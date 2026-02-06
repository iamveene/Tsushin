package main

import (
	"context"
	"database/sql"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"math/rand"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"reflect"
	"strings"
	"sync"
	"syscall"
	"time"

	_ "github.com/mattn/go-sqlite3"
	"github.com/mdp/qrterminal"
	"github.com/skip2/go-qrcode"

	"bytes"

	"go.mau.fi/whatsmeow"
	waProto "go.mau.fi/whatsmeow/binary/proto"
	"go.mau.fi/whatsmeow/store/sqlstore"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	waLog "go.mau.fi/whatsmeow/util/log"
	"google.golang.org/protobuf/proto"
)

// Global QR code storage for API access
var currentQRCode string
var qrCodeMutex sync.RWMutex

// API authentication secret (Phase Security-1: SSRF Prevention)
// Read from MCP_API_SECRET environment variable
var apiSecret string

// Reconnection state management
type ReconnectionState struct {
	mutex              sync.RWMutex
	reconnectAttempts  int
	maxReconnectAttempts int
	lastReconnectTime  time.Time
	lastActivityTime   time.Time
	sessionStartTime   time.Time
	isReconnecting     bool
	needsReauth        bool
}

var reconnectState = &ReconnectionState{
	maxReconnectAttempts: 10,
	sessionStartTime:     time.Time{},
}

// Message represents a chat message for our client
type Message struct {
	Time      time.Time
	Sender    string
	Content   string
	IsFromMe  bool
	MediaType string
	Filename  string
}

// Database handler for storing message history
type MessageStore struct {
	db *sql.DB
}

// Initialize message store
func NewMessageStore() (*MessageStore, error) {
	// Create directory for database if it doesn't exist
	if err := os.MkdirAll("store", 0755); err != nil {
		return nil, fmt.Errorf("failed to create store directory: %v", err)
	}

	// Open SQLite database for messages
	// Use WAL mode for better concurrency and add synchronous=NORMAL for durability
	db, err := sql.Open("sqlite3", "file:store/messages.db?_foreign_keys=on&_journal_mode=WAL&_synchronous=NORMAL")
	if err != nil {
		return nil, fmt.Errorf("failed to open message database: %v", err)
	}

	// Ensure WAL mode is set and verify connection works
	_, err = db.Exec("PRAGMA journal_mode=WAL")
	if err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to set WAL mode: %v", err)
	}
	_, err = db.Exec("PRAGMA synchronous=NORMAL")
	if err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to set synchronous mode: %v", err)
	}

	// Create tables if they don't exist
	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS chats (
			jid TEXT PRIMARY KEY,
			name TEXT,
			last_message_time TIMESTAMP
		);

		CREATE TABLE IF NOT EXISTS messages (
			id TEXT,
			chat_jid TEXT,
			sender TEXT,
			content TEXT,
			timestamp TIMESTAMP,
			is_from_me BOOLEAN,
			media_type TEXT,
			filename TEXT,
			url TEXT,
			media_key BLOB,
			file_sha256 BLOB,
			file_enc_sha256 BLOB,
			file_length INTEGER,
			PRIMARY KEY (id, chat_jid),
			FOREIGN KEY (chat_jid) REFERENCES chats(jid)
		);
	`)
	if err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to create tables: %v", err)
	}

	return &MessageStore{db: db}, nil
}

// Close the database connection
func (store *MessageStore) Close() error {
	return store.db.Close()
}

// StartCheckpointDaemon runs periodic WAL checkpoints to ensure data is synced to disk
// This addresses Docker Desktop gRPC-FUSE filesystem sync issues on macOS
// The daemon runs in a background goroutine and performs FULL checkpoint every 5 seconds
func (store *MessageStore) StartCheckpointDaemon(stopChan <-chan struct{}) {
	go func() {
		ticker := time.NewTicker(5 * time.Second)
		defer ticker.Stop()

		fmt.Println("📦 WAL checkpoint daemon started (5s interval)")

		for {
			select {
			case <-ticker.C:
				// FULL checkpoint mode for maximum durability
				// This transfers all WAL content to the main database file
				_, err := store.db.Exec("PRAGMA wal_checkpoint(FULL)")
				if err != nil {
					fmt.Printf("Warning: Periodic WAL checkpoint failed: %v\n", err)
				}
			case <-stopChan:
				// Final checkpoint before shutdown
				store.db.Exec("PRAGMA wal_checkpoint(TRUNCATE)")
				fmt.Println("📦 WAL checkpoint daemon stopped")
				return
			}
		}
	}()
}

// Store a chat in the database
func (store *MessageStore) StoreChat(jid, name string, lastMessageTime time.Time) error {
	_, err := store.db.Exec(
		"INSERT OR REPLACE INTO chats (jid, name, last_message_time) VALUES (?, ?, ?)",
		jid, name, lastMessageTime,
	)
	if err != nil {
		return err
	}

	// CRITICAL FIX: Force WAL checkpoint after every write to ensure data is synced to disk
	_, checkpointErr := store.db.Exec("PRAGMA wal_checkpoint(PASSIVE)")
	if checkpointErr != nil {
		fmt.Printf("Warning: WAL checkpoint failed: %v\n", checkpointErr)
	}

	return nil
}

// Store a message in the database
func (store *MessageStore) StoreMessage(id, chatJID, sender, content string, timestamp time.Time, isFromMe bool,
	mediaType, filename, url string, mediaKey, fileSHA256, fileEncSHA256 []byte, fileLength uint64) error {
	// Only store if there's actual content or media
	if content == "" && mediaType == "" {
		return nil
	}

	_, err := store.db.Exec(
		`INSERT OR REPLACE INTO messages
		(id, chat_jid, sender, content, timestamp, is_from_me, media_type, filename, url, media_key, file_sha256, file_enc_sha256, file_length)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		id, chatJID, sender, content, timestamp, isFromMe, mediaType, filename, url, mediaKey, fileSHA256, fileEncSHA256, fileLength,
	)
	if err != nil {
		return err
	}

	// CRITICAL FIX: Force WAL checkpoint after every write to ensure data is synced to disk
	// This addresses Docker Desktop gRPC-FUSE filesystem sync issues on macOS
	// PASSIVE mode checkpoints without blocking readers
	_, checkpointErr := store.db.Exec("PRAGMA wal_checkpoint(PASSIVE)")
	if checkpointErr != nil {
		fmt.Printf("Warning: WAL checkpoint failed: %v\n", checkpointErr)
	}

	return nil
}

// Get messages from a chat
func (store *MessageStore) GetMessages(chatJID string, limit int) ([]Message, error) {
	rows, err := store.db.Query(
		"SELECT sender, content, timestamp, is_from_me, media_type, filename FROM messages WHERE chat_jid = ? ORDER BY timestamp DESC LIMIT ?",
		chatJID, limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var messages []Message
	for rows.Next() {
		var msg Message
		var timestamp time.Time
		err := rows.Scan(&msg.Sender, &msg.Content, &timestamp, &msg.IsFromMe, &msg.MediaType, &msg.Filename)
		if err != nil {
			return nil, err
		}
		msg.Time = timestamp
		messages = append(messages, msg)
	}

	return messages, nil
}

// Get all chats
func (store *MessageStore) GetChats() (map[string]time.Time, error) {
	rows, err := store.db.Query("SELECT jid, last_message_time FROM chats ORDER BY last_message_time DESC")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	chats := make(map[string]time.Time)
	for rows.Next() {
		var jid string
		var lastMessageTime time.Time
		err := rows.Scan(&jid, &lastMessageTime)
		if err != nil {
			return nil, err
		}
		chats[jid] = lastMessageTime
	}

	return chats, nil
}

// InteractiveMessageData represents the JSON structure for interactive messages
type InteractiveMessageData struct {
	Type        string                   `json:"type"`
	Header      string                   `json:"header,omitempty"`
	Body        string                   `json:"body,omitempty"`
	Footer      string                   `json:"footer,omitempty"`
	Buttons     []InteractiveButton      `json:"buttons,omitempty"`
	Sections    []InteractiveSection     `json:"sections,omitempty"`
	NativeFlow  *NativeFlowData          `json:"native_flow,omitempty"`
}

type InteractiveButton struct {
	ID    string `json:"id"`
	Title string `json:"title"`
}

type InteractiveSection struct {
	Title string           `json:"title,omitempty"`
	Rows  []InteractiveRow `json:"rows"`
}

type InteractiveRow struct {
	ID          string `json:"id"`
	Title       string `json:"title"`
	Description string `json:"description,omitempty"`
}

type NativeFlowData struct {
	Name       string                 `json:"name,omitempty"`
	Parameters map[string]interface{} `json:"parameters,omitempty"`
}

// formatInteractiveMessage converts an InteractiveMessage to JSON
func formatInteractiveMessage(interactive *waProto.InteractiveMessage) string {
	if interactive == nil {
		return ""
	}

	data := InteractiveMessageData{
		Type: "interactive",
	}

	// Extract header
	if header := interactive.GetHeader(); header != nil {
		if title := header.GetTitle(); title != "" {
			data.Header = title
		} else if docMsg := header.GetDocumentMessage(); docMsg != nil {
			data.Header = "[Document: " + docMsg.GetFileName() + "]"
		} else if imgMsg := header.GetImageMessage(); imgMsg != nil {
			data.Header = "[Image]"
		} else if vidMsg := header.GetVideoMessage(); vidMsg != nil {
			data.Header = "[Video]"
		}
	}

	// Extract body
	if body := interactive.GetBody(); body != nil {
		data.Body = body.GetText()
	}

	// Extract footer
	if footer := interactive.GetFooter(); footer != nil {
		data.Footer = footer.GetText()
	}

	// Extract native flow (used by business bots like Unimed)
	if nativeFlow := interactive.GetNativeFlowMessage(); nativeFlow != nil {
		data.NativeFlow = &NativeFlowData{}
		// Try to parse the JSON parameters
		if paramsJSON := nativeFlow.GetMessageParamsJSON(); paramsJSON != "" {
			var params map[string]interface{}
			if err := json.Unmarshal([]byte(paramsJSON), &params); err == nil {
				data.NativeFlow.Parameters = params
			}
		}
		// Extract buttons from native flow if available
		if buttons := nativeFlow.GetButtons(); len(buttons) > 0 {
			for _, btn := range buttons {
				if btn != nil {
					btnData := InteractiveButton{
						ID:    btn.GetName(),
						Title: btn.GetName(), // Native flow buttons typically use name for both
					}
					// Try to get button params for more details
					if paramsJSON := btn.GetButtonParamsJSON(); paramsJSON != "" {
						var params map[string]interface{}
						if err := json.Unmarshal([]byte(paramsJSON), &params); err == nil {
							if title, ok := params["display_text"].(string); ok {
								btnData.Title = title
							}
							if id, ok := params["id"].(string); ok {
								btnData.ID = id
							}
						}
					}
					data.Buttons = append(data.Buttons, btnData)
				}
			}
		}
	}

	// Extract collection message (product catalogs)
	if collection := interactive.GetCollectionMessage(); collection != nil {
		data.Type = "collection"
		data.Body = collection.GetBizJID()
	}

	// Extract shop storefront message
	if shop := interactive.GetShopStorefrontMessage(); shop != nil {
		data.Type = "shop"
	}

	jsonBytes, err := json.Marshal(data)
	if err != nil {
		return fmt.Sprintf("[Interactive Message - Parse Error: %v]", err)
	}

	return string(jsonBytes)
}

// formatListMessage converts a ListMessage to JSON
func formatListMessage(list *waProto.ListMessage) string {
	if list == nil {
		return ""
	}

	data := InteractiveMessageData{
		Type:   "list",
		Header: list.GetTitle(),
		Body:   list.GetDescription(),
		Footer: list.GetFooterText(),
	}

	// Extract sections and rows
	for _, section := range list.GetSections() {
		if section != nil {
			sec := InteractiveSection{
				Title: section.GetTitle(),
			}
			for _, row := range section.GetRows() {
				if row != nil {
					sec.Rows = append(sec.Rows, InteractiveRow{
						ID:          row.GetRowID(),
						Title:       row.GetTitle(),
						Description: row.GetDescription(),
					})
				}
			}
			data.Sections = append(data.Sections, sec)
		}
	}

	jsonBytes, err := json.Marshal(data)
	if err != nil {
		return fmt.Sprintf("[List Message - Parse Error: %v]", err)
	}

	return string(jsonBytes)
}

// formatButtonsMessage converts a ButtonsMessage to JSON
func formatButtonsMessage(buttons *waProto.ButtonsMessage) string {
	if buttons == nil {
		return ""
	}

	data := InteractiveMessageData{
		Type:   "buttons",
		Header: buttons.GetText(),
		Body:   buttons.GetContentText(),
		Footer: buttons.GetFooterText(),
	}

	// Extract buttons
	for _, btn := range buttons.GetButtons() {
		if btn != nil {
			btnText := btn.GetButtonText()
			if btnText != nil {
				data.Buttons = append(data.Buttons, InteractiveButton{
					ID:    btn.GetButtonID(),
					Title: btnText.GetDisplayText(),
				})
			}
		}
	}

	jsonBytes, err := json.Marshal(data)
	if err != nil {
		return fmt.Sprintf("[Buttons Message - Parse Error: %v]", err)
	}

	return string(jsonBytes)
}

// formatListResponseMessage converts a ListResponseMessage to JSON
func formatListResponseMessage(response *waProto.ListResponseMessage) string {
	if response == nil {
		return ""
	}

	data := map[string]interface{}{
		"type":        "list_response",
		"title":       response.GetTitle(),
		"description": response.GetDescription(),
	}

	if selection := response.GetSingleSelectReply(); selection != nil {
		data["selected_row_id"] = selection.GetSelectedRowID()
	}

	jsonBytes, err := json.Marshal(data)
	if err != nil {
		return fmt.Sprintf("[List Response - Parse Error: %v]", err)
	}

	return string(jsonBytes)
}

// formatButtonsResponseMessage converts a ButtonsResponseMessage to JSON
func formatButtonsResponseMessage(response *waProto.ButtonsResponseMessage) string {
	if response == nil {
		return ""
	}

	data := map[string]interface{}{
		"type":               "buttons_response",
		"selected_button_id": response.GetSelectedButtonID(),
		"selected_display_text": response.GetSelectedDisplayText(),
	}

	jsonBytes, err := json.Marshal(data)
	if err != nil {
		return fmt.Sprintf("[Buttons Response - Parse Error: %v]", err)
	}

	return string(jsonBytes)
}

// Extract text content from a message
func extractTextContent(msg *waProto.Message) string {
	if msg == nil {
		return ""
	}

	// Try to get text content (most common)
	if text := msg.GetConversation(); text != "" {
		return text
	}
	if extendedText := msg.GetExtendedTextMessage(); extendedText != nil {
		return extendedText.GetText()
	}

	// Handle InteractiveMessage (used by business bots like Unimed)
	if interactive := msg.GetInteractiveMessage(); interactive != nil {
		return formatInteractiveMessage(interactive)
	}

	// Handle ListMessage (list menus with sections/rows)
	if list := msg.GetListMessage(); list != nil {
		return formatListMessage(list)
	}

	// Handle ButtonsMessage (simple button menus)
	if buttons := msg.GetButtonsMessage(); buttons != nil {
		return formatButtonsMessage(buttons)
	}

	// Handle ListResponseMessage (user selection from list)
	if listResponse := msg.GetListResponseMessage(); listResponse != nil {
		return formatListResponseMessage(listResponse)
	}

	// Handle ButtonsResponseMessage (user selection from buttons)
	if buttonsResponse := msg.GetButtonsResponseMessage(); buttonsResponse != nil {
		return formatButtonsResponseMessage(buttonsResponse)
	}

	// Handle TemplateMessage (template-based interactive messages)
	if template := msg.GetTemplateMessage(); template != nil {
		if hydratedTemplate := template.GetHydratedTemplate(); hydratedTemplate != nil {
			data := map[string]interface{}{
				"type": "template",
				"body": hydratedTemplate.GetHydratedContentText(),
			}
			// Extract template buttons
			var buttons []InteractiveButton
			for i, btn := range hydratedTemplate.GetHydratedButtons() {
				if btn != nil {
					btnData := InteractiveButton{
						ID: fmt.Sprintf("%d", i),
					}
					if qrBtn := btn.GetQuickReplyButton(); qrBtn != nil {
						btnData.Title = qrBtn.GetDisplayText()
						btnData.ID = qrBtn.GetID()
					} else if urlBtn := btn.GetUrlButton(); urlBtn != nil {
						btnData.Title = urlBtn.GetDisplayText()
					} else if callBtn := btn.GetCallButton(); callBtn != nil {
						btnData.Title = callBtn.GetDisplayText()
					}
					buttons = append(buttons, btnData)
				}
			}
			if len(buttons) > 0 {
				data["buttons"] = buttons
			}
			jsonBytes, _ := json.Marshal(data)
			return string(jsonBytes)
		}
	}

	// Handle TemplateButtonReplyMessage (response to template)
	if templateReply := msg.GetTemplateButtonReplyMessage(); templateReply != nil {
		data := map[string]interface{}{
			"type":          "template_response",
			"selected_id":   templateReply.GetSelectedID(),
			"selected_text": templateReply.GetSelectedDisplayText(),
		}
		jsonBytes, _ := json.Marshal(data)
		return string(jsonBytes)
	}

	// Extract caption from media messages (image, video, document)
	if image := msg.GetImageMessage(); image != nil {
		return image.GetCaption()
	}
	if video := msg.GetVideoMessage(); video != nil {
		return video.GetCaption()
	}
	if document := msg.GetDocumentMessage(); document != nil {
		return document.GetCaption()
	}
	if audio := msg.GetAudioMessage(); audio != nil {
		// Audio typically doesn't have captions, but check anyway
		return ""
	}

	return ""
}

// SendMessageResponse represents the response for the send message API
type SendMessageResponse struct {
	Success bool   `json:"success"`
	Message string `json:"message"`
}

// SendMessageRequest represents the request body for the send message API
type SendMessageRequest struct {
	Recipient string `json:"recipient"`
	Message   string `json:"message"`
	MediaPath string `json:"media_path,omitempty"`
}

// Function to send a WhatsApp message
func sendWhatsAppMessage(client *whatsmeow.Client, recipient string, message string, mediaPath string) (bool, string) {
	if !client.IsConnected() {
		return false, "Not connected to WhatsApp"
	}

	// Create JID for recipient
	var recipientJID types.JID
	var err error

	// Check if recipient is a JID
	isJID := strings.Contains(recipient, "@")

	if isJID {
		// Parse the JID string
		recipientJID, err = types.ParseJID(recipient)
		if err != nil {
			return false, fmt.Sprintf("Error parsing JID: %v", err)
		}
	} else {
		// Normalize phone number - strip leading '+' if present
		// WhatsApp expects numbers without the + prefix (e.g., "5500000000001", not "+5500000000001")
		phoneNumber := strings.TrimPrefix(recipient, "+")

		// Create JID from phone number
		recipientJID = types.JID{
			User:   phoneNumber,
			Server: "s.whatsapp.net", // For personal chats
		}
	}

	msg := &waProto.Message{}

	// Check if we have media to send
	if mediaPath != "" {
		// Read media file
		mediaData, err := os.ReadFile(mediaPath)
		if err != nil {
			return false, fmt.Sprintf("Error reading media file: %v", err)
		}

		// Determine media type and mime type based on file extension
		fileExt := strings.ToLower(mediaPath[strings.LastIndex(mediaPath, ".")+1:])
		var mediaType whatsmeow.MediaType
		var mimeType string

		// Handle different media types
		switch fileExt {
		// Image types
		case "jpg", "jpeg":
			mediaType = whatsmeow.MediaImage
			mimeType = "image/jpeg"
		case "png":
			mediaType = whatsmeow.MediaImage
			mimeType = "image/png"
		case "gif":
			mediaType = whatsmeow.MediaImage
			mimeType = "image/gif"
		case "webp":
			mediaType = whatsmeow.MediaImage
			mimeType = "image/webp"

		// Audio types
		case "ogg":
			mediaType = whatsmeow.MediaAudio
			mimeType = "audio/ogg; codecs=opus"

		// Video types
		case "mp4":
			mediaType = whatsmeow.MediaVideo
			mimeType = "video/mp4"
		case "avi":
			mediaType = whatsmeow.MediaVideo
			mimeType = "video/avi"
		case "mov":
			mediaType = whatsmeow.MediaVideo
			mimeType = "video/quicktime"

		// Document types (for any other file type)
		default:
			mediaType = whatsmeow.MediaDocument
			mimeType = "application/octet-stream"
		}

		// Upload media to WhatsApp servers (with 60s timeout to prevent indefinite hangs)
		uploadCtx, uploadCancel := context.WithTimeout(context.Background(), 60*time.Second)
		defer uploadCancel()
		resp, err := client.Upload(uploadCtx, mediaData, mediaType)
		if err != nil {
			if uploadCtx.Err() == context.DeadlineExceeded {
				return false, "Timeout uploading media to WhatsApp (60s exceeded)"
			}
			return false, fmt.Sprintf("Error uploading media: %v", err)
		}

		fmt.Println("Media uploaded", resp)

		// Create the appropriate message type based on media type
		switch mediaType {
		case whatsmeow.MediaImage:
			msg.ImageMessage = &waProto.ImageMessage{
				Caption:       proto.String(message),
				Mimetype:      proto.String(mimeType),
				URL:           &resp.URL,
				DirectPath:    &resp.DirectPath,
				MediaKey:      resp.MediaKey,
				FileEncSHA256: resp.FileEncSHA256,
				FileSHA256:    resp.FileSHA256,
				FileLength:    &resp.FileLength,
			}
		case whatsmeow.MediaAudio:
			// Handle ogg audio files
			var seconds uint32 = 30 // Default fallback
			var waveform []byte = nil

			// Try to analyze the ogg file
			if strings.Contains(mimeType, "ogg") {
				analyzedSeconds, analyzedWaveform, err := analyzeOggOpus(mediaData)
				if err == nil {
					seconds = analyzedSeconds
					waveform = analyzedWaveform
				} else {
					return false, fmt.Sprintf("Failed to analyze Ogg Opus file: %v", err)
				}
			} else {
				fmt.Printf("Not an Ogg Opus file: %s\n", mimeType)
			}

			msg.AudioMessage = &waProto.AudioMessage{
				Mimetype:      proto.String(mimeType),
				URL:           &resp.URL,
				DirectPath:    &resp.DirectPath,
				MediaKey:      resp.MediaKey,
				FileEncSHA256: resp.FileEncSHA256,
				FileSHA256:    resp.FileSHA256,
				FileLength:    &resp.FileLength,
				Seconds:       proto.Uint32(seconds),
				PTT:           proto.Bool(true),
				Waveform:      waveform,
			}
		case whatsmeow.MediaVideo:
			msg.VideoMessage = &waProto.VideoMessage{
				Caption:       proto.String(message),
				Mimetype:      proto.String(mimeType),
				URL:           &resp.URL,
				DirectPath:    &resp.DirectPath,
				MediaKey:      resp.MediaKey,
				FileEncSHA256: resp.FileEncSHA256,
				FileSHA256:    resp.FileSHA256,
				FileLength:    &resp.FileLength,
			}
		case whatsmeow.MediaDocument:
			msg.DocumentMessage = &waProto.DocumentMessage{
				Title:         proto.String(mediaPath[strings.LastIndex(mediaPath, "/")+1:]),
				Caption:       proto.String(message),
				Mimetype:      proto.String(mimeType),
				URL:           &resp.URL,
				DirectPath:    &resp.DirectPath,
				MediaKey:      resp.MediaKey,
				FileEncSHA256: resp.FileEncSHA256,
				FileSHA256:    resp.FileSHA256,
				FileLength:    &resp.FileLength,
			}
		}
	} else {
		msg.Conversation = proto.String(message)
	}

	// Send message (with 60s timeout to prevent indefinite hangs)
	sendCtx, sendCancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer sendCancel()
	_, err = client.SendMessage(sendCtx, recipientJID, msg)

	if err != nil {
		if sendCtx.Err() == context.DeadlineExceeded {
			return false, "Timeout sending message to WhatsApp (60s exceeded)"
		}
		return false, fmt.Sprintf("Error sending message: %v", err)
	}

	return true, fmt.Sprintf("Message sent to %s", recipient)
}

// Extract media info from a message
func extractMediaInfo(msg *waProto.Message) (mediaType string, filename string, url string, mediaKey []byte, fileSHA256 []byte, fileEncSHA256 []byte, fileLength uint64) {
	if msg == nil {
		return "", "", "", nil, nil, nil, 0
	}

	// Check for image message
	if img := msg.GetImageMessage(); img != nil {
		return "image", "image_" + time.Now().Format("20060102_150405") + ".jpg",
			img.GetURL(), img.GetMediaKey(), img.GetFileSHA256(), img.GetFileEncSHA256(), img.GetFileLength()
	}

	// Check for video message
	if vid := msg.GetVideoMessage(); vid != nil {
		return "video", "video_" + time.Now().Format("20060102_150405") + ".mp4",
			vid.GetURL(), vid.GetMediaKey(), vid.GetFileSHA256(), vid.GetFileEncSHA256(), vid.GetFileLength()
	}

	// Check for audio message
	if aud := msg.GetAudioMessage(); aud != nil {
		return "audio", "audio_" + time.Now().Format("20060102_150405") + ".ogg",
			aud.GetURL(), aud.GetMediaKey(), aud.GetFileSHA256(), aud.GetFileEncSHA256(), aud.GetFileLength()
	}

	// Check for document message
	if doc := msg.GetDocumentMessage(); doc != nil {
		filename := doc.GetFileName()
		if filename == "" {
			filename = "document_" + time.Now().Format("20060102_150405")
		}
		return "document", filename,
			doc.GetURL(), doc.GetMediaKey(), doc.GetFileSHA256(), doc.GetFileEncSHA256(), doc.GetFileLength()
	}

	return "", "", "", nil, nil, nil, 0
}

// Handle regular incoming messages with media support
func handleMessage(client *whatsmeow.Client, messageStore *MessageStore, msg *events.Message, logger waLog.Logger) {
	// CRITICAL DEBUG: Log function entry
	chatJID := msg.Info.Chat.String()
	sender := msg.Info.Sender.User
	fmt.Printf("🔍 handleMessage CALLED: ChatJID=%s, Sender=%s, IsFromMe=%v\n", chatJID, sender, msg.Info.IsFromMe)

	// Save message to database
	// Get appropriate chat name (pass nil for conversation since we don't have one for regular messages)
	name := GetChatName(client, messageStore, msg.Info.Chat, chatJID, nil, sender, logger)

	// Update chat in database with the message timestamp (keeps last message time updated)
	err := messageStore.StoreChat(chatJID, name, msg.Info.Timestamp)
	if err != nil {
		logger.Warnf("Failed to store chat: %v", err)
	}

	// Extract text content
	content := extractTextContent(msg.Message)
	fmt.Printf("🔍 Extracted content length: %d chars\n", len(content))

	// Extract media info
	mediaType, filename, url, mediaKey, fileSHA256, fileEncSHA256, fileLength := extractMediaInfo(msg.Message)
	fmt.Printf("🔍 Media info: type=%s, filename=%s\n", mediaType, filename)

	// Skip if there's no content and no media
	if content == "" && mediaType == "" {
		fmt.Printf("⚠️ SKIPPING: No content and no media\n")
		return
	}

	// CRITICAL DEBUG: Log before storage attempt
	fmt.Printf("DEBUG: Attempting to store message - ID=%s, ChatJID=%s, Content=%s, HasMedia=%v\n",
		msg.Info.ID, chatJID, content[:min(50, len(content))], mediaType != "")

	// Store message in database
	err = messageStore.StoreMessage(
		msg.Info.ID,
		chatJID,
		sender,
		content,
		msg.Info.Timestamp,
		msg.Info.IsFromMe,
		mediaType,
		filename,
		url,
		mediaKey,
		fileSHA256,
		fileEncSHA256,
		fileLength,
	)

	if err != nil {
		// CRITICAL: Always log storage failures
		fmt.Printf("❌ STORAGE FAILED: %v (ID=%s, ChatJID=%s)\n", err, msg.Info.ID, chatJID)
		logger.Warnf("Failed to store message: %v", err)
	} else {
		// CRITICAL DEBUG: Confirm successful storage
		fmt.Printf("✅ STORAGE SUCCESS: ID=%s stored in %s\n", msg.Info.ID, chatJID)

		// Log message reception
		timestamp := msg.Info.Timestamp.Format("2006-01-02 15:04:05")
		direction := "←"
		if msg.Info.IsFromMe {
			direction = "→"
		}

		// Log based on message type
		if mediaType != "" {
			fmt.Printf("[%s] %s %s: [%s: %s] %s\n", timestamp, direction, sender, mediaType, filename, content)
		} else if content != "" {
			fmt.Printf("[%s] %s %s: %s\n", timestamp, direction, sender, content)
		}
	}
}

// DownloadMediaRequest represents the request body for the download media API
type DownloadMediaRequest struct {
	MessageID string `json:"message_id"`
	ChatJID   string `json:"chat_jid"`
}

// DownloadMediaResponse represents the response for the download media API
type DownloadMediaResponse struct {
	Success     bool   `json:"success"`
	Message     string `json:"message"`
	Filename    string `json:"filename,omitempty"`
	Path        string `json:"path,omitempty"`
	FileContent string `json:"file_content,omitempty"` // Base64-encoded file bytes for container isolation
}

// Store additional media info in the database
func (store *MessageStore) StoreMediaInfo(id, chatJID, url string, mediaKey, fileSHA256, fileEncSHA256 []byte, fileLength uint64) error {
	_, err := store.db.Exec(
		"UPDATE messages SET url = ?, media_key = ?, file_sha256 = ?, file_enc_sha256 = ?, file_length = ? WHERE id = ? AND chat_jid = ?",
		url, mediaKey, fileSHA256, fileEncSHA256, fileLength, id, chatJID,
	)
	return err
}

// Get media info from the database
func (store *MessageStore) GetMediaInfo(id, chatJID string) (string, string, string, []byte, []byte, []byte, uint64, error) {
	var mediaType, filename, url string
	var mediaKey, fileSHA256, fileEncSHA256 []byte
	var fileLength uint64

	err := store.db.QueryRow(
		"SELECT media_type, filename, url, media_key, file_sha256, file_enc_sha256, file_length FROM messages WHERE id = ? AND chat_jid = ?",
		id, chatJID,
	).Scan(&mediaType, &filename, &url, &mediaKey, &fileSHA256, &fileEncSHA256, &fileLength)

	return mediaType, filename, url, mediaKey, fileSHA256, fileEncSHA256, fileLength, err
}

// MediaDownloader implements the whatsmeow.DownloadableMessage interface
type MediaDownloader struct {
	URL           string
	DirectPath    string
	MediaKey      []byte
	FileLength    uint64
	FileSHA256    []byte
	FileEncSHA256 []byte
	MediaType     whatsmeow.MediaType
}

// GetDirectPath implements the DownloadableMessage interface
func (d *MediaDownloader) GetDirectPath() string {
	return d.DirectPath
}

// GetURL implements the DownloadableMessage interface
func (d *MediaDownloader) GetURL() string {
	return d.URL
}

// GetMediaKey implements the DownloadableMessage interface
func (d *MediaDownloader) GetMediaKey() []byte {
	return d.MediaKey
}

// GetFileLength implements the DownloadableMessage interface
func (d *MediaDownloader) GetFileLength() uint64 {
	return d.FileLength
}

// GetFileSHA256 implements the DownloadableMessage interface
func (d *MediaDownloader) GetFileSHA256() []byte {
	return d.FileSHA256
}

// GetFileEncSHA256 implements the DownloadableMessage interface
func (d *MediaDownloader) GetFileEncSHA256() []byte {
	return d.FileEncSHA256
}

// GetMediaType implements the DownloadableMessage interface
func (d *MediaDownloader) GetMediaType() whatsmeow.MediaType {
	return d.MediaType
}

// Function to download media from a message
func downloadMedia(client *whatsmeow.Client, messageStore *MessageStore, messageID, chatJID string) (bool, string, string, string, error) {
	// Query the database for the message
	var mediaType, filename, url string
	var mediaKey, fileSHA256, fileEncSHA256 []byte
	var fileLength uint64
	var err error

	// First, check if we already have this file
	chatDir := fmt.Sprintf("store/%s", strings.ReplaceAll(chatJID, ":", "_"))
	localPath := ""

	// Get media info from the database
	mediaType, filename, url, mediaKey, fileSHA256, fileEncSHA256, fileLength, err = messageStore.GetMediaInfo(messageID, chatJID)

	if err != nil {
		// Try to get basic info if extended info isn't available
		err = messageStore.db.QueryRow(
			"SELECT media_type, filename FROM messages WHERE id = ? AND chat_jid = ?",
			messageID, chatJID,
		).Scan(&mediaType, &filename)

		if err != nil {
			return false, "", "", "", fmt.Errorf("failed to find message: %v", err)
		}
	}

	// Check if this is a media message
	if mediaType == "" {
		return false, "", "", "", fmt.Errorf("not a media message")
	}

	// Create directory for the chat if it doesn't exist
	if err := os.MkdirAll(chatDir, 0755); err != nil {
		return false, "", "", "", fmt.Errorf("failed to create chat directory: %v", err)
	}

	// Generate a local path for the file
	localPath = fmt.Sprintf("%s/%s", chatDir, filename)

	// Get absolute path
	absPath, err := filepath.Abs(localPath)
	if err != nil {
		return false, "", "", "", fmt.Errorf("failed to get absolute path: %v", err)
	}

	// Check if file already exists
	if _, err := os.Stat(localPath); err == nil {
		// File exists, return it
		return true, mediaType, filename, absPath, nil
	}

	// If we don't have all the media info we need, we can't download
	if url == "" || len(mediaKey) == 0 || len(fileSHA256) == 0 || len(fileEncSHA256) == 0 || fileLength == 0 {
		return false, "", "", "", fmt.Errorf("incomplete media information for download")
	}

	fmt.Printf("Attempting to download media for message %s in chat %s...\n", messageID, chatJID)

	// Extract direct path from URL
	directPath := extractDirectPathFromURL(url)

	// Create a downloader that implements DownloadableMessage
	var waMediaType whatsmeow.MediaType
	switch mediaType {
	case "image":
		waMediaType = whatsmeow.MediaImage
	case "video":
		waMediaType = whatsmeow.MediaVideo
	case "audio":
		waMediaType = whatsmeow.MediaAudio
	case "document":
		waMediaType = whatsmeow.MediaDocument
	default:
		return false, "", "", "", fmt.Errorf("unsupported media type: %s", mediaType)
	}

	downloader := &MediaDownloader{
		URL:           url,
		DirectPath:    directPath,
		MediaKey:      mediaKey,
		FileLength:    fileLength,
		FileSHA256:    fileSHA256,
		FileEncSHA256: fileEncSHA256,
		MediaType:     waMediaType,
	}

	// Download the media using whatsmeow client
	mediaData, err := client.Download(context.Background(), downloader)
	if err != nil {
		return false, "", "", "", fmt.Errorf("failed to download media: %v", err)
	}

	// Save the downloaded media to file
	if err := os.WriteFile(localPath, mediaData, 0644); err != nil {
		return false, "", "", "", fmt.Errorf("failed to save media file: %v", err)
	}

	fmt.Printf("Successfully downloaded %s media to %s (%d bytes)\n", mediaType, absPath, len(mediaData))
	return true, mediaType, filename, absPath, nil
}

// Extract direct path from a WhatsApp media URL
func extractDirectPathFromURL(url string) string {
	// The direct path is typically in the URL, we need to extract it
	// Example URL: https://mmg.whatsapp.net/v/t62.7118-24/13812002_698058036224062_3424455886509161511_n.enc?ccb=11-4&oh=...

	// Find the path part after the domain
	parts := strings.SplitN(url, ".net/", 2)
	if len(parts) < 2 {
		return url // Return original URL if parsing fails
	}

	pathPart := parts[1]

	// Remove query parameters
	pathPart = strings.SplitN(pathPart, "?", 2)[0]

	// Create proper direct path format
	return "/" + pathPart
}

// authMiddleware provides token-based authentication for MCP API endpoints
// Phase Security-1: SSRF Prevention - prevents cross-tenant MCP access
// Skips authentication for /api/health (required for Docker health checks)
func authMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// Skip auth for health endpoint (Docker health checks need to work without auth)
		if r.URL.Path == "/api/health" {
			next(w, r)
			return
		}

		// If no secret configured, allow all requests (backward compatibility during migration)
		if apiSecret == "" {
			next(w, r)
			return
		}

		// Validate Bearer token
		auth := r.Header.Get("Authorization")
		if auth == "" {
			w.Header().Set("Content-Type", "application/json")
			http.Error(w, `{"error": "Authorization header required"}`, http.StatusUnauthorized)
			return
		}

		if !strings.HasPrefix(auth, "Bearer ") {
			w.Header().Set("Content-Type", "application/json")
			http.Error(w, `{"error": "Invalid authorization format, expected Bearer token"}`, http.StatusUnauthorized)
			return
		}

		token := strings.TrimPrefix(auth, "Bearer ")
		if token != apiSecret {
			w.Header().Set("Content-Type", "application/json")
			http.Error(w, `{"error": "Invalid API secret"}`, http.StatusForbidden)
			return
		}

		// Token valid, proceed to handler
		next(w, r)
	}
}

// Start a REST API server to expose the WhatsApp client functionality
func startRESTServer(client *whatsmeow.Client, messageStore *MessageStore, port int) {
	// Read API secret from environment (Phase Security-1)
	apiSecret = os.Getenv("MCP_API_SECRET")
	if apiSecret == "" {
		fmt.Println("⚠️  WARNING: MCP_API_SECRET not set - API endpoints are unprotected!")
	} else {
		fmt.Println("🔒 MCP API authentication enabled")
	}
	// Handler for sending messages
	http.HandleFunc("/api/send", authMiddleware(func(w http.ResponseWriter, r *http.Request) {
		// Only allow POST requests
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		// Parse the request body
		var req SendMessageRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "Invalid request format", http.StatusBadRequest)
			return
		}

		// Validate request
		if req.Recipient == "" {
			http.Error(w, "Recipient is required", http.StatusBadRequest)
			return
		}

		if req.Message == "" && req.MediaPath == "" {
			http.Error(w, "Message or media path is required", http.StatusBadRequest)
			return
		}

		fmt.Println("Received request to send message", req.Message, req.MediaPath)

		// Send the message
		success, message := sendWhatsAppMessage(client, req.Recipient, req.Message, req.MediaPath)
		fmt.Println("Message sent", success, message)
		// Set response headers
		w.Header().Set("Content-Type", "application/json")

		// Set appropriate status code
		if !success {
			w.WriteHeader(http.StatusInternalServerError)
		}

		// Send response
		json.NewEncoder(w).Encode(SendMessageResponse{
			Success: success,
			Message: message,
		})
	}))

	// Health check endpoint with detailed session state (NO AUTH - Docker health checks)
	http.HandleFunc("/api/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)

		reconnectState.mutex.RLock()
		reconnectAttempts := reconnectState.reconnectAttempts
		needsReauth := reconnectState.needsReauth
		isReconnecting := reconnectState.isReconnecting
		lastActivity := reconnectState.lastActivityTime
		sessionStart := reconnectState.sessionStartTime
		reconnectState.mutex.RUnlock()

		// Calculate session age
		var sessionAgeSec int64
		if !sessionStart.IsZero() {
			sessionAgeSec = int64(time.Since(sessionStart).Seconds())
		}

		// Calculate time since last activity
		var lastActivitySec int64
		if !lastActivity.IsZero() {
			lastActivitySec = int64(time.Since(lastActivity).Seconds())
		}

		// Use IsLoggedIn() to check actual authentication status, not just websocket connection
		// IsConnected() only checks if websocket is open to WhatsApp servers
		// IsLoggedIn() checks if we have a valid device session (QR code was scanned)
		authenticated := client.IsLoggedIn()
		connected := client.IsConnected()

		json.NewEncoder(w).Encode(map[string]interface{}{
			"status":             "healthy",
			"connected":          connected,
			"authenticated":      authenticated,
			"needs_reauth":       needsReauth,
			"is_reconnecting":    isReconnecting,
			"reconnect_attempts": reconnectAttempts,
			"session_age_sec":    sessionAgeSec,
			"last_activity_sec":  lastActivitySec,
		})
	})

	// QR code endpoint (returns base64-encoded PNG QR code)
	http.HandleFunc("/api/qr-code", authMiddleware(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		// Check if client is truly authenticated (not just has stored credentials)
		// needsReauth is set when user logs out from phone (events.LoggedOut)
		reconnectState.mutex.RLock()
		needsReauth := reconnectState.needsReauth
		reconnectState.mutex.RUnlock()

		// Only report "Already authenticated" if BOTH:
		// 1. client.IsLoggedIn() returns true (has stored credentials)
		// 2. needsReauth is false (user didn't logout from phone)
		if client.IsLoggedIn() && !needsReauth {
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(map[string]interface{}{
				"qr_code": nil,
				"message": "Already authenticated",
			})
			return
		}

		// Return stored QR code if available
		qrCodeMutex.RLock()
		qr := currentQRCode
		qrCodeMutex.RUnlock()

		w.WriteHeader(http.StatusOK)
		if qr != "" {
			json.NewEncoder(w).Encode(map[string]interface{}{
				"qr_code": qr,
				"message": "Scan QR code with WhatsApp",
			})
		} else {
			json.NewEncoder(w).Encode(map[string]interface{}{
				"qr_code": nil,
				"message": "QR code not available yet, container starting...",
			})
		}
	}))

	// Logout endpoint (unpairs device from WhatsApp account)
	http.HandleFunc("/api/logout", authMiddleware(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		w.Header().Set("Content-Type", "application/json")

		if !client.IsLoggedIn() {
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(map[string]interface{}{
				"success": true,
				"message": "Already logged out",
			})
			return
		}

		err := client.Logout(context.Background())
		if err != nil {
			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(map[string]interface{}{
				"success": false,
				"message": fmt.Sprintf("Logout failed: %v", err),
			})
			return
		}

		qrCodeMutex.Lock()
		currentQRCode = ""
		qrCodeMutex.Unlock()

		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"success": true,
			"message": "Device successfully unpaired from WhatsApp",
		})
	}))

	// Handler for downloading media
	http.HandleFunc("/api/download", authMiddleware(func(w http.ResponseWriter, r *http.Request) {
		// Only allow POST requests
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		// Parse the request body
		var req DownloadMediaRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "Invalid request format", http.StatusBadRequest)
			return
		}

		// Validate request
		if req.MessageID == "" || req.ChatJID == "" {
			http.Error(w, "Message ID and Chat JID are required", http.StatusBadRequest)
			return
		}

		// Download the media
		success, mediaType, filename, path, err := downloadMedia(client, messageStore, req.MessageID, req.ChatJID)

		// Set response headers
		w.Header().Set("Content-Type", "application/json")

		// Handle download result
		if !success || err != nil {
			errMsg := "Unknown error"
			if err != nil {
				errMsg = err.Error()
			}

			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(DownloadMediaResponse{
				Success: false,
				Message: fmt.Sprintf("Failed to download media: %s", errMsg),
			})
			return
		}

		// Read the file content to send back to backend
		// This is necessary because backend and MCP run in separate containers
		fileData, err := os.ReadFile(path)
		if err != nil {
			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(DownloadMediaResponse{
				Success: false,
				Message: fmt.Sprintf("Failed to read downloaded file: %s", err.Error()),
			})
			return
		}

		// Encode file content as base64 to send via JSON
		fileBase64 := base64.StdEncoding.EncodeToString(fileData)

		// Send successful response with file content
		json.NewEncoder(w).Encode(DownloadMediaResponse{
			Success:     true,
			Message:     fmt.Sprintf("Successfully downloaded %s media", mediaType),
			Filename:    filename,
			Path:        path,
			FileContent: fileBase64, // Add base64-encoded file content
		})
	}))

	// Handler for selecting an option from interactive menus (list/buttons)
	http.HandleFunc("/api/select-option", authMiddleware(func(w http.ResponseWriter, r *http.Request) {
		// Only allow POST requests
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		// Parse the request body
		var req struct {
			Recipient    string `json:"recipient"`      // JID of the bot/chat
			SelectedID   string `json:"selected_id"`    // The ID of the selected option
			SelectedText string `json:"selected_text"`  // Display text of selection (optional)
			ResponseType string `json:"response_type"`  // "list", "buttons", or "native_flow"
		}

		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "Invalid request format", http.StatusBadRequest)
			return
		}

		// Validate request
		if req.Recipient == "" {
			http.Error(w, "Recipient is required", http.StatusBadRequest)
			return
		}
		if req.SelectedID == "" {
			http.Error(w, "Selected ID is required", http.StatusBadRequest)
			return
		}

		// Default response type - native_flow works best with most business bots
		// as it sends the selection as plain text which bots universally accept
		if req.ResponseType == "" {
			req.ResponseType = "native_flow"
		}

		// Parse recipient JID
		var recipientJID types.JID
		var err error

		if strings.Contains(req.Recipient, "@") {
			recipientJID, err = types.ParseJID(req.Recipient)
			if err != nil {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusBadRequest)
				json.NewEncoder(w).Encode(SendMessageResponse{
					Success: false,
					Message: fmt.Sprintf("Invalid recipient JID: %v", err),
				})
				return
			}
		} else {
			phoneNumber := strings.TrimPrefix(req.Recipient, "+")
			recipientJID = types.JID{
				User:   phoneNumber,
				Server: "s.whatsapp.net",
			}
		}

		// Build the response message based on type
		var msg *waProto.Message

		switch req.ResponseType {
		case "list":
			// ListResponseMessage for list menu selections
			msg = &waProto.Message{
				ListResponseMessage: &waProto.ListResponseMessage{
					Title:       proto.String(req.SelectedText),
					ListType:    waProto.ListResponseMessage_SINGLE_SELECT.Enum(),
					SingleSelectReply: &waProto.ListResponseMessage_SingleSelectReply{
						SelectedRowID: proto.String(req.SelectedID),
					},
				},
			}

		case "buttons":
			// ButtonsResponseMessage for button selections
			msg = &waProto.Message{
				ButtonsResponseMessage: &waProto.ButtonsResponseMessage{
					SelectedButtonID: proto.String(req.SelectedID),
					Type:             waProto.ButtonsResponseMessage_DISPLAY_TEXT.Enum(),
				},
			}

		case "native_flow":
			// For native flow buttons, we typically just send the button text as a regular message
			// Many bots accept the button text as a text reply
			msg = &waProto.Message{
				Conversation: proto.String(req.SelectedID),
			}

		default:
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusBadRequest)
			json.NewEncoder(w).Encode(SendMessageResponse{
				Success: false,
				Message: fmt.Sprintf("Invalid response_type: %s (use 'list', 'buttons', or 'native_flow')", req.ResponseType),
			})
			return
		}

		// Send the response message
		sendCtx, sendCancel := context.WithTimeout(context.Background(), 60*time.Second)
		defer sendCancel()

		_, err = client.SendMessage(sendCtx, recipientJID, msg)

		w.Header().Set("Content-Type", "application/json")

		if err != nil {
			if sendCtx.Err() == context.DeadlineExceeded {
				w.WriteHeader(http.StatusInternalServerError)
				json.NewEncoder(w).Encode(SendMessageResponse{
					Success: false,
					Message: "Timeout sending selection to WhatsApp (60s exceeded)",
				})
				return
			}
			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(SendMessageResponse{
				Success: false,
				Message: fmt.Sprintf("Error sending selection: %v", err),
			})
			return
		}

		json.NewEncoder(w).Encode(SendMessageResponse{
			Success: true,
			Message: fmt.Sprintf("Selection '%s' sent to %s", req.SelectedID, req.Recipient),
		})
	}))

	// Handler for checking if phone numbers are registered on WhatsApp
	// This endpoint uses the IsOnWhatsApp API to resolve phone numbers to WhatsApp JIDs
	http.HandleFunc("/api/check-numbers", authMiddleware(func(w http.ResponseWriter, r *http.Request) {
		// Only allow POST requests
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		// Check if client is connected and authenticated
		if !client.IsLoggedIn() {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusServiceUnavailable)
			json.NewEncoder(w).Encode(map[string]interface{}{
				"success": false,
				"message": "WhatsApp client not authenticated",
			})
			return
		}

		// Parse the request body
		var req struct {
			PhoneNumbers []string `json:"phone_numbers"`
		}

		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "Invalid request format", http.StatusBadRequest)
			return
		}

		// Validate request
		if len(req.PhoneNumbers) == 0 {
			http.Error(w, "phone_numbers array is required and must not be empty", http.StatusBadRequest)
			return
		}

		// Limit batch size to avoid rate limiting (max 50 numbers per call)
		if len(req.PhoneNumbers) > 50 {
			http.Error(w, "Maximum 50 phone numbers per request", http.StatusBadRequest)
			return
		}

		fmt.Printf("Checking %d phone numbers on WhatsApp...\n", len(req.PhoneNumbers))

		// Normalize phone numbers (remove + prefix, ensure only digits)
		normalizedNumbers := make([]string, len(req.PhoneNumbers))
		for i, phone := range req.PhoneNumbers {
			// Remove + prefix and any non-digit characters
			normalized := strings.TrimPrefix(phone, "+")
			// Keep only digits
			var digits strings.Builder
			for _, r := range normalized {
				if r >= '0' && r <= '9' {
					digits.WriteRune(r)
				}
			}
			normalizedNumbers[i] = digits.String()
		}

		// Call IsOnWhatsApp to check if numbers are registered
		results, err := client.IsOnWhatsApp(normalizedNumbers)
		if err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(map[string]interface{}{
				"success": false,
				"message": fmt.Sprintf("Failed to check numbers: %v", err),
			})
			return
		}

		// Build response with original phone numbers mapped to results
		type CheckResult struct {
			Phone        string `json:"phone"`
			IsRegistered bool   `json:"is_registered"`
			JID          string `json:"jid,omitempty"`
		}

		responseResults := make([]CheckResult, len(results))
		for i, result := range results {
			checkResult := CheckResult{
				Phone:        req.PhoneNumbers[i], // Use original phone number from request
				IsRegistered: result.IsIn,
			}
			if result.IsIn && result.JID.User != "" {
				// Return the full JID string (e.g., "5500000000001@s.whatsapp.net")
				checkResult.JID = result.JID.String()
			}
			responseResults[i] = checkResult

			if result.IsIn {
				fmt.Printf("  ✅ %s → %s\n", req.PhoneNumbers[i], result.JID.String())
			} else {
				fmt.Printf("  ❌ %s → not registered\n", req.PhoneNumbers[i])
			}
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"success": true,
			"results": responseResults,
		})
	}))

	// Handler for getting new messages (bypasses filesystem sync issues)
	// This endpoint allows the backend watcher to poll for new messages via HTTP
	// instead of reading SQLite directly from bind-mounted volumes
	http.HandleFunc("/api/messages", authMiddleware(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		// Get 'since' parameter (timestamp string or Unix epoch)
		sinceParam := r.URL.Query().Get("since")
		limitParam := r.URL.Query().Get("limit")

		// Default limit to 100
		limit := 100
		if limitParam != "" {
			if parsed, err := fmt.Sscanf(limitParam, "%d", &limit); err != nil || parsed != 1 {
				limit = 100
			}
			if limit > 500 {
				limit = 500
			}
		}

		// Parse 'since' timestamp
		var sinceTime time.Time
		if sinceParam != "" {
			// Try parsing as RFC3339/ISO8601 first
			if t, err := time.Parse(time.RFC3339, sinceParam); err == nil {
				sinceTime = t
			} else if t, err := time.Parse("2006-01-02 15:04:05", sinceParam); err == nil {
				sinceTime = t
			} else if t, err := time.Parse("2006-01-02 15:04:05+00:00", sinceParam); err == nil {
				sinceTime = t
			} else {
				// Try as Unix timestamp
				var epoch int64
				if _, err := fmt.Sscanf(sinceParam, "%d", &epoch); err == nil {
					sinceTime = time.Unix(epoch, 0)
				} else {
					sinceTime = time.Unix(0, 0) // Default to epoch
				}
			}
		} else {
			sinceTime = time.Unix(0, 0)
		}

		// Query messages from database
		query := `
			SELECT
				m.id,
				m.chat_jid,
				c.name as chat_name,
				m.sender,
				m.content,
				m.timestamp,
				m.is_from_me,
				m.media_type,
				m.filename,
				m.url
			FROM messages m
			LEFT JOIN chats c ON m.chat_jid = c.jid
			WHERE m.timestamp > ? AND m.is_from_me = 0
			ORDER BY m.timestamp ASC
			LIMIT ?
		`

		rows, err := messageStore.db.Query(query, sinceTime.Format("2006-01-02 15:04:05+00:00"), limit)
		if err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(map[string]interface{}{
				"success": false,
				"error":   fmt.Sprintf("Database query failed: %v", err),
			})
			return
		}
		defer rows.Close()

		// Build response
		type MessageResponse struct {
			ID        string `json:"id"`
			ChatJID   string `json:"chat_jid"`
			ChatName  string `json:"chat_name,omitempty"`
			Sender    string `json:"sender"`
			Content   string `json:"content"`
			Timestamp string `json:"timestamp"`
			IsFromMe  bool   `json:"is_from_me"`
			MediaType string `json:"media_type,omitempty"`
			Filename  string `json:"filename,omitempty"`
			MediaURL  string `json:"media_url,omitempty"`
		}

		var messages []MessageResponse
		for rows.Next() {
			var msg MessageResponse
			var chatName, mediaType, filename, mediaURL sql.NullString

			err := rows.Scan(
				&msg.ID,
				&msg.ChatJID,
				&chatName,
				&msg.Sender,
				&msg.Content,
				&msg.Timestamp,
				&msg.IsFromMe,
				&mediaType,
				&filename,
				&mediaURL,
			)
			if err != nil {
				continue
			}

			if chatName.Valid {
				msg.ChatName = chatName.String
			}
			if mediaType.Valid {
				msg.MediaType = mediaType.String
			}
			if filename.Valid {
				msg.Filename = filename.String
			}
			if mediaURL.Valid {
				msg.MediaURL = mediaURL.String
			}

			messages = append(messages, msg)
		}

		// Return messages
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"success":  true,
			"messages": messages,
			"count":    len(messages),
		})
	}))

	// Handler for getting the latest message timestamp
	// Used by the backend to determine starting point for polling
	http.HandleFunc("/api/messages/latest", authMiddleware(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		// Query for the latest message timestamp
		var latestTimestamp sql.NullString
		err := messageStore.db.QueryRow(`
			SELECT MAX(timestamp) FROM messages WHERE is_from_me = 0
		`).Scan(&latestTimestamp)

		if err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(map[string]interface{}{
				"success": false,
				"error":   fmt.Sprintf("Database query failed: %v", err),
			})
			return
		}

		w.Header().Set("Content-Type", "application/json")
		if latestTimestamp.Valid && latestTimestamp.String != "" {
			json.NewEncoder(w).Encode(map[string]interface{}{
				"success":          true,
				"latest_timestamp": latestTimestamp.String,
			})
		} else {
			json.NewEncoder(w).Encode(map[string]interface{}{
				"success":          true,
				"latest_timestamp": nil,
			})
		}
	}))

	// Start the server
	serverAddr := fmt.Sprintf(":%d", port)
	fmt.Printf("Starting REST API server on %s...\n", serverAddr)

	// Run server in a goroutine so it doesn't block
	go func() {
		if err := http.ListenAndServe(serverAddr, nil); err != nil {
			fmt.Printf("REST API server error: %v\n", err)
		}
	}()
}

// updateActivityTime updates the last activity timestamp
func updateActivityTime() {
	reconnectState.mutex.Lock()
	reconnectState.lastActivityTime = time.Now()
	reconnectState.mutex.Unlock()
}

// calculateBackoffDuration calculates exponential backoff with jitter
func calculateBackoffDuration(attempt int) time.Duration {
	// Base: 1s, 2s, 4s, 8s, 16s, 32s, 60s (max)
	maxDuration := 60 * time.Second
	baseDuration := time.Duration(1<<uint(attempt)) * time.Second

	if baseDuration > maxDuration {
		baseDuration = maxDuration
	}

	// Add jitter (±25%)
	jitter := time.Duration(rand.Int63n(int64(baseDuration) / 2))
	return baseDuration + jitter
}

// attemptReconnect handles reconnection with exponential backoff
func attemptReconnect(client *whatsmeow.Client, logger waLog.Logger) bool {
	reconnectState.mutex.Lock()

	// Check if we've exceeded max attempts
	if reconnectState.reconnectAttempts >= reconnectState.maxReconnectAttempts {
		logger.Errorf("Maximum reconnection attempts (%d) reached. Manual re-authentication required.", reconnectState.maxReconnectAttempts)
		reconnectState.needsReauth = true
		reconnectState.isReconnecting = false
		reconnectState.mutex.Unlock()
		return false
	}

	// Check if we should throttle reconnection attempts
	timeSinceLastAttempt := time.Since(reconnectState.lastReconnectTime)
	requiredBackoff := calculateBackoffDuration(reconnectState.reconnectAttempts)

	if timeSinceLastAttempt < requiredBackoff {
		reconnectState.mutex.Unlock()
		return false // Too soon to retry
	}

	reconnectState.reconnectAttempts++
	reconnectState.lastReconnectTime = time.Now()
	reconnectState.isReconnecting = true
	attempt := reconnectState.reconnectAttempts
	reconnectState.mutex.Unlock()

	logger.Infof("Attempting reconnection (attempt %d/%d) after %v backoff...",
		attempt, reconnectState.maxReconnectAttempts, requiredBackoff)

	// Attempt to reconnect
	err := client.Connect()
	if err != nil {
		logger.Errorf("Reconnection attempt %d failed: %v", attempt, err)
		reconnectState.mutex.Lock()
		reconnectState.isReconnecting = false
		reconnectState.mutex.Unlock()
		return false
	}

	// Wait a moment to verify connection
	time.Sleep(2 * time.Second)

	if client.IsConnected() && client.IsLoggedIn() {
		logger.Infof("✅ Reconnection successful on attempt %d", attempt)
		reconnectState.mutex.Lock()
		reconnectState.reconnectAttempts = 0
		reconnectState.isReconnecting = false
		reconnectState.needsReauth = false
		reconnectState.mutex.Unlock()
		updateActivityTime()
		return true
	}

	logger.Warnf("Reconnection attempt %d: connected but not authenticated", attempt)
	reconnectState.mutex.Lock()
	reconnectState.isReconnecting = false
	reconnectState.mutex.Unlock()
	return false
}

// startKeepalive sends periodic presence updates to maintain session
func startKeepalive(client *whatsmeow.Client, logger waLog.Logger, stopChan <-chan struct{}) {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if client.IsConnected() && client.IsLoggedIn() {
				// Send presence available to keep session alive
				err := client.SendPresence(types.PresenceAvailable)
				if err != nil {
					logger.Warnf("Failed to send keepalive presence: %v", err)
				} else {
					logger.Debugf("Keepalive sent successfully")
					updateActivityTime()
				}
			}
		case <-stopChan:
			logger.Infof("Keepalive goroutine stopped")
			return
		}
	}
}

func main() {
	// Parse command-line flags
	var port int
	flag.IntVar(&port, "port", 8080, "Port for REST API server (default: 8080)")
	flag.Parse()

	// Set up logger
	logger := waLog.Stdout("Client", "INFO", true)
	logger.Infof("Starting WhatsApp client...")

	// Create database connection for storing session data
	dbLog := waLog.Stdout("Database", "INFO", true)

	// Create directory for database if it doesn't exist
	if err := os.MkdirAll("store", 0755); err != nil {
		logger.Errorf("Failed to create store directory: %v", err)
		return
	}

	container, err := sqlstore.New(context.Background(), "sqlite3", "file:store/whatsapp.db?_foreign_keys=on", dbLog)
	if err != nil {
		logger.Errorf("Failed to connect to database: %v", err)
		return
	}

	// Get device store - This contains session information
	deviceStore, err := container.GetFirstDevice(context.Background())
	if err != nil {
		if err == sql.ErrNoRows {
			// No device exists, create one
			deviceStore = container.NewDevice()
			logger.Infof("Created new device")
		} else {
			logger.Errorf("Failed to get device: %v", err)
			return
		}
	}

	// Create client instance
	client := whatsmeow.NewClient(deviceStore, logger)
	if client == nil {
		logger.Errorf("Failed to create WhatsApp client")
		return
	}

	// Initialize message store
	messageStore, err := NewMessageStore()
	if err != nil {
		logger.Errorf("Failed to initialize message store: %v", err)
		return
	}
	defer messageStore.Close()

	// Start WAL checkpoint daemon for Docker filesystem sync
	// This ensures messages are synced to disk even when Docker Desktop gRPC-FUSE has issues
	checkpointStopChan := make(chan struct{})
	defer close(checkpointStopChan)
	messageStore.StartCheckpointDaemon(checkpointStopChan)

	// Setup event handling for messages and history sync
	client.AddEventHandler(func(evt interface{}) {
		switch v := evt.(type) {
		case *events.Message:
			// Process regular messages
			handleMessage(client, messageStore, v, logger)
			updateActivityTime()

		case *events.HistorySync:
			// Process history sync events
			handleHistorySync(client, messageStore, v, logger)
			updateActivityTime()

		case *events.Connected:
			logger.Infof("✅ Connected to WhatsApp")
			reconnectState.mutex.Lock()
			reconnectState.reconnectAttempts = 0
			reconnectState.needsReauth = false
			if reconnectState.sessionStartTime.IsZero() {
				reconnectState.sessionStartTime = time.Now()
			}
			reconnectState.mutex.Unlock()
			updateActivityTime()

		case *events.Disconnected:
			logger.Warnf("⚠️  Disconnected from WhatsApp")

			// Attempt automatic reconnection
			go func() {
				time.Sleep(2 * time.Second) // Brief pause before reconnecting
				if !client.IsConnected() {
					attemptReconnect(client, logger)
				}
			}()

		case *events.LoggedOut:
			logger.Errorf("❌ Device logged out from WhatsApp (user unlinked from phone)")
			reconnectState.mutex.Lock()
			reconnectState.needsReauth = true
			reconnectState.reconnectAttempts = 0
			reconnectState.mutex.Unlock()

			// Clear QR code to force regeneration
			qrCodeMutex.Lock()
			currentQRCode = ""
			qrCodeMutex.Unlock()

			// Trigger QR regeneration by deleting device and reconnecting
			// This is required because client.Store.ID remains set after logout
			go func() {
				logger.Infof("Triggering QR regeneration after logout...")
				time.Sleep(1 * time.Second) // Brief pause

				// Disconnect first
				client.Disconnect()
				time.Sleep(500 * time.Millisecond)

				// Delete the device from the store - this clears the stored credentials
				// and allows a fresh QR code to be generated
				logger.Infof("Deleting device from store to allow re-pairing...")
				if err := client.Store.Delete(context.Background()); err != nil {
					logger.Errorf("Failed to delete device from store: %v", err)
					// Continue anyway - the needsReauth flag will prevent false positives
				} else {
					logger.Infof("Device deleted from store successfully")
				}

				// Get a new QR channel and connect
				// Since the device is deleted, this will generate a new QR code
				logger.Infof("Getting QR channel for re-authentication...")
				qrChan, _ := client.GetQRChannel(context.Background())

				err := client.Connect()
				if err != nil {
					logger.Errorf("Failed to reconnect after logout: %v", err)
					return
				}

				// Process QR events
				for evt := range qrChan {
					if evt.Event == "code" {
						qrPNG, err := qrcode.Encode(evt.Code, qrcode.Medium, 256)
						if err == nil {
							qrCodeMutex.Lock()
							currentQRCode = base64.StdEncoding.EncodeToString(qrPNG)
							qrCodeMutex.Unlock()
							logger.Infof("✅ New QR code generated after logout")
						}
					} else if evt.Event == "success" {
						// User scanned the new QR code
						qrCodeMutex.Lock()
						currentQRCode = ""
						qrCodeMutex.Unlock()
						reconnectState.mutex.Lock()
						reconnectState.needsReauth = false
						reconnectState.mutex.Unlock()
						logger.Infof("✅ Successfully re-authenticated after logout")
						break
					}
				}
			}()

		case *events.StreamReplaced:
			logger.Warnf("⚠️  Stream replaced - another device logged in with same session")
			reconnectState.mutex.Lock()
			reconnectState.needsReauth = true
			reconnectState.mutex.Unlock()

		case *events.StreamError:
			logger.Errorf("❌ Stream error: %v", v)

			// Attempt reconnection for stream errors
			go func() {
				time.Sleep(5 * time.Second) // Wait a bit longer for stream errors
				if !client.IsConnected() {
					attemptReconnect(client, logger)
				}
			}()

		case *events.TemporaryBan:
			logger.Errorf("❌ Temporary ban from WhatsApp. Code: %s, Expire: %v", v.Code, v.Expire)
			reconnectState.mutex.Lock()
			reconnectState.reconnectAttempts = reconnectState.maxReconnectAttempts // Stop trying
			reconnectState.mutex.Unlock()
		}
	})

	// Create channels for keepalive management
	keepaliveStopChan := make(chan struct{})
	defer close(keepaliveStopChan)

	// Create channel to track connection success
	connected := make(chan bool, 1)

	// Start REST API server BEFORE authentication (so QR code can be retrieved via API)
	startRESTServer(client, messageStore, port)
	fmt.Println("REST server started on port", port)

	// Connect to WhatsApp
	if client.Store.ID == nil {
		// No ID stored, this is a new client, need to pair with phone
		// Process QR codes in a goroutine with automatic regeneration
		// This allows continuous QR refresh until authentication succeeds
		go func() {
			for {
				// Get a new QR channel for each batch of codes
				qrChan, _ := client.GetQRChannel(context.Background())

				if !client.IsConnected() {
					err := client.Connect()
					if err != nil {
						logger.Errorf("Failed to connect for QR: %v", err)
						time.Sleep(5 * time.Second)
						continue
					}
				}

				qrExpired := false
				for evt := range qrChan {
					if evt.Event == "code" {
						fmt.Println("\nScan this QR code with your WhatsApp app:")
						qrterminal.GenerateHalfBlock(evt.Code, qrterminal.L, os.Stdout)

						// Store QR code as base64 PNG for API access
						qrPNG, err := qrcode.Encode(evt.Code, qrcode.Medium, 256)
						if err == nil {
							qrCodeMutex.Lock()
							currentQRCode = base64.StdEncoding.EncodeToString(qrPNG)
							qrCodeMutex.Unlock()
							logger.Infof("QR code updated (new code available for scanning)")
						}
					} else if evt.Event == "success" {
						// Clear QR code on success
						qrCodeMutex.Lock()
						currentQRCode = ""
						qrCodeMutex.Unlock()
						connected <- true
						logger.Infof("QR code authentication successful")
						return
					} else if evt.Event == "timeout" {
						// QR batch expired - will get new channel in outer loop
						logger.Infof("QR code batch expired, regenerating new codes...")
						qrExpired = true
					}
				}

				// Channel closed - if QR expired, get a new batch
				if qrExpired {
					logger.Infof("Getting new QR code batch...")
					client.Disconnect()
					time.Sleep(2 * time.Second)
					continue
				}

				// Channel closed unexpectedly - check if we're authenticated
				if client.IsLoggedIn() {
					logger.Infof("QR channel closed - client is authenticated")
					connected <- true
					return
				}

				// Not authenticated and channel closed - retry after delay
				logger.Warnf("QR channel closed unexpectedly, retrying...")
				time.Sleep(5 * time.Second)
			}
		}()

		// Wait for connection - the goroutine handles QR regeneration indefinitely
		select {
		case <-connected:
			fmt.Println("\nSuccessfully connected and authenticated!")
		case <-time.After(60 * time.Minute):
			// After 60 minutes, log but DON'T exit - keep server running
			logger.Warnf("QR code not scanned for 60 minutes - server continues running")
		}
	} else {
		// Already logged in, just connect
		err = client.Connect()
		if err != nil {
			logger.Errorf("Failed to connect: %v", err)
			return
		}
		connected <- true
	}

	// Wait a moment for connection to stabilize
	time.Sleep(2 * time.Second)

	if !client.IsConnected() {
		logger.Errorf("Failed to establish stable connection")
		return
	}

	// Initialize session start time
	reconnectState.mutex.Lock()
	reconnectState.sessionStartTime = time.Now()
	reconnectState.reconnectAttempts = 0
	reconnectState.needsReauth = false
	reconnectState.mutex.Unlock()
	updateActivityTime()

	fmt.Println("\n✓ Connected to WhatsApp! Type 'help' for commands.")

	// Start keepalive goroutine to maintain session
	go startKeepalive(client, logger, keepaliveStopChan)
	logger.Infof("✅ Keepalive mechanism started (30s interval)")

	// REST API server already started earlier (before authentication)

	// Create a channel to keep the main goroutine alive
	exitChan := make(chan os.Signal, 1)
	signal.Notify(exitChan, syscall.SIGINT, syscall.SIGTERM)

	fmt.Println("REST server is running. Press Ctrl+C to disconnect and exit.")

	// Wait for termination signal
	<-exitChan

	fmt.Println("Disconnecting...")
	// Disconnect client
	client.Disconnect()
}

// GetChatName determines the appropriate name for a chat based on JID and other info
func GetChatName(client *whatsmeow.Client, messageStore *MessageStore, jid types.JID, chatJID string, conversation interface{}, sender string, logger waLog.Logger) string {
	// First, check if chat already exists in database with a name
	var existingName string
	err := messageStore.db.QueryRow("SELECT name FROM chats WHERE jid = ?", chatJID).Scan(&existingName)
	if err == nil && existingName != "" {
		// Chat exists with a name, use that
		logger.Infof("Using existing chat name for %s: %s", chatJID, existingName)
		return existingName
	}

	// Need to determine chat name
	var name string

	if jid.Server == "g.us" {
		// This is a group chat
		logger.Infof("Getting name for group: %s", chatJID)

		// Use conversation data if provided (from history sync)
		if conversation != nil {
			// Extract name from conversation if available
			// This uses type assertions to handle different possible types
			var displayName, convName *string
			// Try to extract the fields we care about regardless of the exact type
			v := reflect.ValueOf(conversation)
			if v.Kind() == reflect.Ptr && !v.IsNil() {
				v = v.Elem()

				// Try to find DisplayName field
				if displayNameField := v.FieldByName("DisplayName"); displayNameField.IsValid() && displayNameField.Kind() == reflect.Ptr && !displayNameField.IsNil() {
					dn := displayNameField.Elem().String()
					displayName = &dn
				}

				// Try to find Name field
				if nameField := v.FieldByName("Name"); nameField.IsValid() && nameField.Kind() == reflect.Ptr && !nameField.IsNil() {
					n := nameField.Elem().String()
					convName = &n
				}
			}

			// Use the name we found
			if displayName != nil && *displayName != "" {
				name = *displayName
			} else if convName != nil && *convName != "" {
				name = *convName
			}
		}

		// If we didn't get a name, try group info
		if name == "" {
			groupInfo, err := client.GetGroupInfo(jid)
			if err == nil && groupInfo.Name != "" {
				name = groupInfo.Name
			} else {
				// Fallback name for groups
				name = fmt.Sprintf("Group %s", jid.User)
			}
		}

		logger.Infof("Using group name: %s", name)
	} else {
		// This is an individual contact
		logger.Infof("Getting name for contact: %s", chatJID)

		// Just use contact info (full name)
		contact, err := client.Store.Contacts.GetContact(context.Background(), jid)
		if err == nil && contact.FullName != "" {
			name = contact.FullName
		} else if sender != "" {
			// Fallback to sender
			name = sender
		} else {
			// Last fallback to JID
			name = jid.User
		}

		logger.Infof("Using contact name: %s", name)
	}

	return name
}

// Handle history sync events
func handleHistorySync(client *whatsmeow.Client, messageStore *MessageStore, historySync *events.HistorySync, logger waLog.Logger) {
	fmt.Printf("Received history sync event with %d conversations\n", len(historySync.Data.Conversations))

	syncedCount := 0
	for _, conversation := range historySync.Data.Conversations {
		// Parse JID from the conversation
		if conversation.ID == nil {
			continue
		}

		chatJID := *conversation.ID

		// Try to parse the JID
		jid, err := types.ParseJID(chatJID)
		if err != nil {
			logger.Warnf("Failed to parse JID %s: %v", chatJID, err)
			continue
		}

		// Get appropriate chat name by passing the history sync conversation directly
		name := GetChatName(client, messageStore, jid, chatJID, conversation, "", logger)

		// Process messages
		messages := conversation.Messages
		if len(messages) > 0 {
			// Update chat with latest message timestamp
			latestMsg := messages[0]
			if latestMsg == nil || latestMsg.Message == nil {
				continue
			}

			// Get timestamp from message info
			timestamp := time.Time{}
			if ts := latestMsg.Message.GetMessageTimestamp(); ts != 0 {
				timestamp = time.Unix(int64(ts), 0)
			} else {
				continue
			}

			messageStore.StoreChat(chatJID, name, timestamp)

			// Store messages
			for _, msg := range messages {
				if msg == nil || msg.Message == nil {
					continue
				}

				// Extract text content
				var content string
				if msg.Message.Message != nil {
					if conv := msg.Message.Message.GetConversation(); conv != "" {
						content = conv
					} else if ext := msg.Message.Message.GetExtendedTextMessage(); ext != nil {
						content = ext.GetText()
					}
				}

				// Extract media info
				var mediaType, filename, url string
				var mediaKey, fileSHA256, fileEncSHA256 []byte
				var fileLength uint64

				if msg.Message.Message != nil {
					mediaType, filename, url, mediaKey, fileSHA256, fileEncSHA256, fileLength = extractMediaInfo(msg.Message.Message)
				}

				// Log the message content for debugging
				logger.Infof("Message content: %v, Media Type: %v", content, mediaType)

				// Skip messages with no content and no media
				if content == "" && mediaType == "" {
					continue
				}

				// Determine sender
				var sender string
				isFromMe := false
				if msg.Message.Key != nil {
					if msg.Message.Key.FromMe != nil {
						isFromMe = *msg.Message.Key.FromMe
					}
					if !isFromMe && msg.Message.Key.Participant != nil && *msg.Message.Key.Participant != "" {
						sender = *msg.Message.Key.Participant
					} else if isFromMe {
						sender = client.Store.ID.User
					} else {
						sender = jid.User
					}
				} else {
					sender = jid.User
				}

				// Store message
				msgID := ""
				if msg.Message.Key != nil && msg.Message.Key.ID != nil {
					msgID = *msg.Message.Key.ID
				}

				// Get message timestamp
				timestamp := time.Time{}
				if ts := msg.Message.GetMessageTimestamp(); ts != 0 {
					timestamp = time.Unix(int64(ts), 0)
				} else {
					continue
				}

				err = messageStore.StoreMessage(
					msgID,
					chatJID,
					sender,
					content,
					timestamp,
					isFromMe,
					mediaType,
					filename,
					url,
					mediaKey,
					fileSHA256,
					fileEncSHA256,
					fileLength,
				)
				if err != nil {
					logger.Warnf("Failed to store history message: %v", err)
				} else {
					syncedCount++
					// Log successful message storage
					if mediaType != "" {
						logger.Infof("Stored message: [%s] %s -> %s: [%s: %s] %s",
							timestamp.Format("2006-01-02 15:04:05"), sender, chatJID, mediaType, filename, content)
					} else {
						logger.Infof("Stored message: [%s] %s -> %s: %s",
							timestamp.Format("2006-01-02 15:04:05"), sender, chatJID, content)
					}
				}
			}
		}
	}

	fmt.Printf("History sync complete. Stored %d messages.\n", syncedCount)
}

// Request history sync from the server
func requestHistorySync(client *whatsmeow.Client) {
	if client == nil {
		fmt.Println("Client is not initialized. Cannot request history sync.")
		return
	}

	if !client.IsConnected() {
		fmt.Println("Client is not connected. Please ensure you are connected to WhatsApp first.")
		return
	}

	if client.Store.ID == nil {
		fmt.Println("Client is not logged in. Please scan the QR code first.")
		return
	}

	// Build and send a history sync request
	historyMsg := client.BuildHistorySyncRequest(nil, 100)
	if historyMsg == nil {
		fmt.Println("Failed to build history sync request.")
		return
	}

	_, err := client.SendMessage(context.Background(), types.JID{
		Server: "s.whatsapp.net",
		User:   "status",
	}, historyMsg)

	if err != nil {
		fmt.Printf("Failed to request history sync: %v\n", err)
	} else {
		fmt.Println("History sync requested. Waiting for server response...")
	}
}

// analyzeOggOpus tries to extract duration and generate a simple waveform from an Ogg Opus file
func analyzeOggOpus(data []byte) (duration uint32, waveform []byte, err error) {
	// Try to detect if this is a valid Ogg file by checking for the "OggS" signature
	// at the beginning of the file
	if len(data) < 4 || string(data[0:4]) != "OggS" {
		return 0, nil, fmt.Errorf("not a valid Ogg file (missing OggS signature)")
	}

	// Parse Ogg pages to find the last page with a valid granule position
	var lastGranule uint64
	var sampleRate uint32 = 48000 // Default Opus sample rate
	var preSkip uint16 = 0
	var foundOpusHead bool

	// Scan through the file looking for Ogg pages
	for i := 0; i < len(data); {
		// Check if we have enough data to read Ogg page header
		if i+27 >= len(data) {
			break
		}

		// Verify Ogg page signature
		if string(data[i:i+4]) != "OggS" {
			// Skip until next potential page
			i++
			continue
		}

		// Extract header fields
		granulePos := binary.LittleEndian.Uint64(data[i+6 : i+14])
		pageSeqNum := binary.LittleEndian.Uint32(data[i+18 : i+22])
		numSegments := int(data[i+26])

		// Extract segment table
		if i+27+numSegments >= len(data) {
			break
		}
		segmentTable := data[i+27 : i+27+numSegments]

		// Calculate page size
		pageSize := 27 + numSegments
		for _, segLen := range segmentTable {
			pageSize += int(segLen)
		}

		// Check if we're looking at an OpusHead packet (should be in first few pages)
		if !foundOpusHead && pageSeqNum <= 1 {
			// Look for "OpusHead" marker in this page
			pageData := data[i : i+pageSize]
			headPos := bytes.Index(pageData, []byte("OpusHead"))
			if headPos >= 0 && headPos+12 < len(pageData) {
				// Found OpusHead, extract sample rate and pre-skip
				// OpusHead format: Magic(8) + Version(1) + Channels(1) + PreSkip(2) + SampleRate(4) + ...
				headPos += 8 // Skip "OpusHead" marker
				// PreSkip is 2 bytes at offset 10
				if headPos+12 <= len(pageData) {
					preSkip = binary.LittleEndian.Uint16(pageData[headPos+10 : headPos+12])
					sampleRate = binary.LittleEndian.Uint32(pageData[headPos+12 : headPos+16])
					foundOpusHead = true
					fmt.Printf("Found OpusHead: sampleRate=%d, preSkip=%d\n", sampleRate, preSkip)
				}
			}
		}

		// Keep track of last valid granule position
		if granulePos != 0 {
			lastGranule = granulePos
		}

		// Move to next page
		i += pageSize
	}

	if !foundOpusHead {
		fmt.Println("Warning: OpusHead not found, using default values")
	}

	// Calculate duration based on granule position
	if lastGranule > 0 {
		// Formula for duration: (lastGranule - preSkip) / sampleRate
		durationSeconds := float64(lastGranule-uint64(preSkip)) / float64(sampleRate)
		duration = uint32(math.Ceil(durationSeconds))
		fmt.Printf("Calculated Opus duration from granule: %f seconds (lastGranule=%d)\n",
			durationSeconds, lastGranule)
	} else {
		// Fallback to rough estimation if granule position not found
		fmt.Println("Warning: No valid granule position found, using estimation")
		durationEstimate := float64(len(data)) / 2000.0 // Very rough approximation
		duration = uint32(durationEstimate)
	}

	// Make sure we have a reasonable duration (at least 1 second, at most 300 seconds)
	if duration < 1 {
		duration = 1
	} else if duration > 300 {
		duration = 300
	}

	// Generate waveform
	waveform = placeholderWaveform(duration)

	fmt.Printf("Ogg Opus analysis: size=%d bytes, calculated duration=%d sec, waveform=%d bytes\n",
		len(data), duration, len(waveform))

	return duration, waveform, nil
}

// min returns the smaller of x or y
func min(x, y int) int {
	if x < y {
		return x
	}
	return y
}

// placeholderWaveform generates a synthetic waveform for WhatsApp voice messages
// that appears natural with some variability based on the duration
func placeholderWaveform(duration uint32) []byte {
	// WhatsApp expects a 64-byte waveform for voice messages
	const waveformLength = 64
	waveform := make([]byte, waveformLength)

	// Seed the random number generator for consistent results with the same duration
	rand.Seed(int64(duration))

	// Create a more natural looking waveform with some patterns and variability
	// rather than completely random values

	// Base amplitude and frequency - longer messages get faster frequency
	baseAmplitude := 35.0
	frequencyFactor := float64(min(int(duration), 120)) / 30.0

	for i := range waveform {
		// Position in the waveform (normalized 0-1)
		pos := float64(i) / float64(waveformLength)

		// Create a wave pattern with some randomness
		// Use multiple sine waves of different frequencies for more natural look
		val := baseAmplitude * math.Sin(pos*math.Pi*frequencyFactor*8)
		val += (baseAmplitude / 2) * math.Sin(pos*math.Pi*frequencyFactor*16)

		// Add some randomness to make it look more natural
		val += (rand.Float64() - 0.5) * 15

		// Add some fade-in and fade-out effects
		fadeInOut := math.Sin(pos * math.Pi)
		val = val * (0.7 + 0.3*fadeInOut)

		// Center around 50 (typical voice baseline)
		val = val + 50

		// Ensure values stay within WhatsApp's expected range (0-100)
		if val < 0 {
			val = 0
		} else if val > 100 {
			val = 100
		}

		waveform[i] = byte(val)
	}

	return waveform
}

package main

import (
	"testing"

	"go.mau.fi/whatsmeow/store"
)

func TestSetWAVersionUpdatesLoginPayload(t *testing.T) {
	original := store.GetWAVersion()
	t.Cleanup(func() {
		store.SetWAVersion(original)
	})

	replacement := store.WAVersionContainer{
		original[0],
		original[1],
		original[2] + 1,
	}
	store.SetWAVersion(replacement)

	payloadVersion := store.BaseClientPayload.GetUserAgent().GetAppVersion()
	if payloadVersion.GetPrimary() != replacement[0] ||
		payloadVersion.GetSecondary() != replacement[1] ||
		payloadVersion.GetTertiary() != replacement[2] {
		t.Fatalf(
			"login payload version = %d.%d.%d, want %s",
			payloadVersion.GetPrimary(),
			payloadVersion.GetSecondary(),
			payloadVersion.GetTertiary(),
			replacement,
		)
	}
}

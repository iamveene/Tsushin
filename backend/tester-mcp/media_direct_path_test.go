package main

import "testing"

func TestExtractDirectPathFromURLPreservesSignedQuery(t *testing.T) {
	t.Parallel()

	got := extractDirectPathFromURL(
		"https://mmg.whatsapp.net/v/t62.7117-24/audio.enc?ccb=11-4&oh=a%2Fb%3D%3D&token=x+y",
	)
	want := "/v/t62.7117-24/audio.enc?ccb=11-4&oh=a%2Fb%3D%3D&token=x+y"
	if got != want {
		t.Fatalf("extractDirectPathFromURL() = %q, want %q", got, want)
	}
}

func TestExtractDirectPathFromURLAcceptsDirectPath(t *testing.T) {
	t.Parallel()

	const directPath = "/v/t62.7117-24/audio.enc?ccb=11-4&oh=signed-value"
	if got := extractDirectPathFromURL(directPath); got != directPath {
		t.Fatalf("extractDirectPathFromURL() = %q, want %q", got, directPath)
	}
}

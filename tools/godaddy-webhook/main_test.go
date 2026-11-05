package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/cert-manager/cert-manager/pkg/acme/webhook/apis/acme/v1alpha1"
)

func TestTarget(t *testing.T) {
	for _, fqdn := range []string{"_acme-challenge.int.andreybondarenko.com.", "_acme-challenge.grafana.int.andreybondarenko.com."} {
		if _, err := target(&v1alpha1.ChallengeRequest{ResolvedFQDN: fqdn, Key: "value"}); err != nil {
			t.Fatal(err)
		}
	}
	for _, fqdn := range []string{"_acme-challenge.andreybondarenko.com.", "_acme-challenge.evilint.andreybondarenko.com.", "_acme-challenge.int.andreybondarenko.com.evil.", "grafana.int.andreybondarenko.com."} {
		if _, err := target(&v1alpha1.ChallengeRequest{ResolvedFQDN: fqdn, Key: "value"}); err == nil {
			t.Fatalf("accepted %s", fqdn)
		}
	}
}

func TestPresentAndRestartSafeCleanup(t *testing.T) {
	records := []record{{ID: "unrelated", Name: "_acme-challenge.grafana.int", Type: "TXT", Data: "another-order", TTL: 600}}
	creates, deletes := 0, 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer test-only-token" {
			t.Error("missing bearer auth")
		}
		switch r.Method {
		case "GET":
			json.NewEncoder(w).Encode(page{Items: records})
		case "POST":
			var entry record
			if err := json.NewDecoder(r.Body).Decode(&entry); err != nil {
				t.Error(err)
			}
			if entry.Data != "already-hashed-value" || entry.Name != "_acme-challenge.grafana.int" || entry.TTL != 600 {
				t.Error("incorrect TXT payload")
			}
			entry.ID = "owned"
			records = append(records, entry)
			creates++
			w.WriteHeader(201)
		case "DELETE":
			if !strings.HasSuffix(r.URL.Path, "/owned") {
				t.Error("deleted unrelated record")
			}
			records = records[:1]
			deletes++
			w.WriteHeader(204)
		default:
			t.Error("unexpected operation")
		}
	}))
	defer server.Close()
	tokenFile := filepath.Join(t.TempDir(), "token")
	if err := os.WriteFile(tokenFile, []byte("test-only-token\n"), 0600); err != nil {
		t.Fatal(err)
	}
	newSolver := func() *solver { return &solver{client: server.Client(), baseURL: server.URL, tokenFile: tokenFile} }
	challenge := &v1alpha1.ChallengeRequest{ResolvedFQDN: "_acme-challenge.grafana.int.andreybondarenko.com.", Key: "already-hashed-value"}
	s := newSolver()
	if err := s.Present(challenge); err != nil {
		t.Fatal(err)
	}
	if err := s.Present(challenge); err != nil {
		t.Fatal(err)
	}
	if creates != 1 {
		t.Fatalf("created %d records", creates)
	}
	s = newSolver()
	if err := s.CleanUp(challenge); err != nil {
		t.Fatal(err)
	}
	if err := s.CleanUp(challenge); err != nil {
		t.Fatal(err)
	}
	if deletes != 1 || len(records) != 1 || records[0].ID != "unrelated" {
		t.Fatal("cleanup failed to preserve unrelated challenge")
	}
}

func TestCredentialNotExposedOnFailure(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(403)
		w.Write([]byte("secret-error-content"))
	}))
	defer server.Close()
	path := filepath.Join(t.TempDir(), "token")
	os.WriteFile(path, []byte("test-only-token"), 0600)
	s := &solver{client: server.Client(), baseURL: server.URL, tokenFile: path}
	err := s.Present(&v1alpha1.ChallengeRequest{ResolvedFQDN: "_acme-challenge.int.andreybondarenko.com.", Key: "value"})
	if err == nil || strings.Contains(err.Error(), "test-only-token") || strings.Contains(err.Error(), "secret-error-content") {
		t.Fatal("unsafe error reporting")
	}
}

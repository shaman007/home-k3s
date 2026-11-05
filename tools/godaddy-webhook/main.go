package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/cert-manager/cert-manager/pkg/acme/webhook/apis/acme/v1alpha1"
	"github.com/cert-manager/cert-manager/pkg/acme/webhook/cmd"
	"k8s.io/client-go/rest"
)

const zone = "andreybondarenko.com"
const suffix = "int.andreybondarenko.com"

type solver struct {
	client             *http.Client
	baseURL, tokenFile string
	mu                 sync.Mutex
}
type record struct {
	ID   string `json:"recordId,omitempty"`
	Name string `json:"name"`
	Type string `json:"type"`
	Data string `json:"data"`
	TTL  int    `json:"ttl"`
}
type page struct {
	Items []record `json:"items"`
}

func (*solver) Name() string                                   { return "godaddy-v3" }
func (*solver) Initialize(*rest.Config, <-chan struct{}) error { return nil }

func target(ch *v1alpha1.ChallengeRequest) (string, error) {
	fqdn := strings.ToLower(strings.TrimSuffix(ch.ResolvedFQDN, "."))
	// Reject delegated challenges and every name outside the selected internal suffix.
	if fqdn != "_acme-challenge."+suffix && !strings.HasSuffix(fqdn, "."+suffix) {
		return "", fmt.Errorf("challenge is outside the allowed internal suffix")
	}
	if !strings.HasPrefix(fqdn, "_acme-challenge.") || ch.Key == "" {
		return "", fmt.Errorf("invalid DNS challenge")
	}
	return strings.TrimSuffix(fqdn, "."+zone), nil
}

func (s *solver) request(method, path string, body any, result any) error {
	token, err := os.ReadFile(s.tokenFile)
	if err != nil || len(bytes.TrimSpace(token)) == 0 {
		return fmt.Errorf("GoDaddy credential unavailable")
	}
	var data io.Reader
	if body != nil {
		payload, err := json.Marshal(body)
		if err != nil {
			return fmt.Errorf("invalid record payload")
		}
		data = bytes.NewReader(payload)
	}
	req, err := http.NewRequest(method, s.baseURL+"/v3/domains/zones/"+zone+"/dns-records"+path, data)
	if err != nil {
		return fmt.Errorf("invalid API request")
	}
	req.Header.Set("Authorization", "Bearer "+string(bytes.TrimSpace(token)))
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.client.Do(req)
	if err != nil {
		return fmt.Errorf("GoDaddy request failed")
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("GoDaddy %s returned HTTP %d", method, resp.StatusCode)
	}
	if result != nil {
		if err := json.NewDecoder(io.LimitReader(resp.Body, 2<<20)).Decode(result); err != nil {
			return fmt.Errorf("invalid GoDaddy response")
		}
	}
	return nil
}

func (s *solver) matches(name, value string) ([]record, error) {
	var records []record
	for p := 1; p <= 1000; p++ {
		var response page
		query := fmt.Sprintf("?type=TXT&name=%s&page=%d&pageSize=100", url.QueryEscape(name), p)
		if err := s.request("GET", query, nil, &response); err != nil {
			return nil, err
		}
		for _, r := range response.Items {
			if r.Type == "TXT" && r.Name == name && r.Data == value {
				records = append(records, r)
			}
		}
		if len(response.Items) < 100 {
			return records, nil
		}
	}
	return nil, fmt.Errorf("GoDaddy pagination limit exceeded")
}

func (s *solver) Present(ch *v1alpha1.ChallengeRequest) error {
	name, err := target(ch)
	if err != nil {
		return err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	matches, err := s.matches(name, ch.Key)
	if err != nil {
		return err
	}
	if len(matches) > 0 {
		return nil
	}
	// ch.Key is already the DNS TXT value, unlike a Lego keyAuthorization.
	return s.request("POST", "", record{Name: name, Type: "TXT", Data: ch.Key, TTL: 600}, nil)
}
func (s *solver) CleanUp(ch *v1alpha1.ChallengeRequest) error {
	name, err := target(ch)
	if err != nil {
		return err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	matches, err := s.matches(name, ch.Key)
	if err != nil {
		return err
	}
	// Re-discover IDs: cleanup remains safe after restarts and preserves other TXT values.
	for _, r := range matches {
		if r.ID == "" {
			return fmt.Errorf("missing GoDaddy record ID")
		}
		if err := s.request("DELETE", "/"+url.PathEscape(r.ID), nil, nil); err != nil {
			return err
		}
	}
	return nil
}

func main() {
	// Disable upstream HTTP debug output: it could expose bearer credentials.
	client := &http.Client{Timeout: 30 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return fmt.Errorf("redirect refused") }}
	cmd.RunWebhookServer("acme.int.andreybondarenko.com", &solver{client: client, baseURL: "https://api.godaddy.com", tokenFile: "/var/run/godaddy/token"})
}

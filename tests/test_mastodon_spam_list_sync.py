"""Exercise the embedded Rails importer with in-memory models and HTTP responses."""

import json
import shutil
import subprocess
from pathlib import Path

import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = yaml.safe_load((ROOT / "mastodon/config-map-spam-list-sync.yaml").read_text())["data"][
    "sync.rb"
]

HARNESS = r"""
require 'net/http'
require 'json'
class Net::HTTP
  def self.start(*)
    client = Object.new
    def client.get(path)
      body = case path.split('/').last
      when 'spam-domains.txt'
        (1..100).map { |i| "spam#{i}.example" }.join("\n") + ENV.fetch('EXTRA_DOMAIN', '')
      when 'spam-mx-servers.txt'
        "mx.spam.example\nsmtp.google.com\ncommunications\n"
      when 'spam-ips.txt'
        ENV.fetch('TEST_RANGE', '198.51.100.0/24')
      end
      response = Net::HTTPOK.new('1.1', '200', 'OK')
      response.instance_variable_set(:@read, true)
      response.body = body
      response
    end
    yield client
  end
end
class Integer
  def days; self * 86400; end
  def from_now; Time.now + self; end
end
module ActiveRecord
  class Base
    def self.transaction; yield; end
    def self.connection; self; end
    def self.execute(*); end
  end
end
class EmailDomainBlock
  def self.exists?(domain:); domain == 'spam1.example'; end
  def self.create!(**args)
    raise 'unexpected write' unless ENV['SPAM_LIST_APPLY'] == 'true'
    Struct.new(:id).new(1)
  end
end
class IpBlock
  def self.find_by(**)
    # Existing manual rule must never be overwritten or refreshed.
    Struct.new(:comment, :severity).new('manual', 'no_access')
  end
  def self.create!(**); raise 'must preserve manual IP rule'; end
end
"""


def run_import(**env):
    import os

    return subprocess.run(
        ["ruby", "-e", HARNESS + SCRIPT],
        env={**os.environ, **env},
        text=True,
        capture_output=True,
        check=False,
    )


@unittest.skipUnless(shutil.which("ruby"), "Ruby required")
class SpamListSyncTest(unittest.TestCase):
    def test_preview_and_apply_preserve_manual_rules(self):
        for apply in ("false", "true"):
            with self.subTest(apply=apply):
                result = run_import(SPAM_LIST_APPLY=apply)
                self.assertEqual(result.returncode, 0, result.stderr)
                summary = json.loads(result.stdout.splitlines()[-1])
                self.assertEqual(summary["apply"], apply == "true")
                self.assertEqual(summary["mx"], 1)
                self.assertEqual(summary["email_added"], 100)
                self.assertEqual(summary["ip_added"], 0)
                self.assertEqual(summary["ip_refreshed"], 0)

    def test_bad_source_fails_before_writes(self):
        for env in [
            {"EXTRA_DOMAIN": "\nnot-a-domain"},
            {"EXTRA_DOMAIN": "\ngmail.com"},
            {"TEST_RANGE": "0.0.0.0/0"},
            {"TEST_RANGE": "127.0.0.1/32"},
            {"TEST_RANGE": "invalid"},
        ]:
            with self.subTest(env=env):
                result = run_import(SPAM_LIST_APPLY="true", **env)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Created ", result.stdout)


if __name__ == "__main__":
    unittest.main()

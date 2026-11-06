#!/usr/bin/perl
use strict;
use warnings;
use JSON::PP qw(decode_json);
use IO::Socket::INET;

# Only aggregate postqueue's JSON output; never log payloads or error text.
sub collect {
    my ($input, $now) = @_;
    my (%counts, %ages);
    for my $name (qw(active deferred incoming hold maildrop)) {
        $counts{$name} = 0;
        $ages{$name} = 0;
    }
    while (my $line = <$input>) {
        die "oversized record" if length($line) > 1048576;
        my $item = decode_json($line);
        my $queue = $item->{queue_name};
        die "unknown queue" unless defined($queue) && exists $counts{$queue};
        my $arrival = $item->{arrival_time};
        die "invalid timestamp" unless defined($arrival) && $arrival =~ /^\d+$/;
        $counts{$queue}++;
        # A message can arrive while postqueue streams its snapshot.
        my $age = $now > $arrival ? $now - $arrival : 0;
        $ages{$queue} = $age if $age > $ages{$queue};
    }
    my $body = "# TYPE postfix_queue_messages gauge\n# TYPE postfix_queue_oldest_age_seconds gauge\n";
    for my $queue (sort keys %counts) {
        $body .= "postfix_queue_messages{queue=\"$queue\"} $counts{$queue}\n";
        $body .= "postfix_queue_oldest_age_seconds{queue=\"$queue\"} $ages{$queue}\n";
    }
    return $body;
}

if (@ARGV && $ARGV[0] eq '--parse') {
    print collect(\*STDIN, $ARGV[1] // time);
    exit;
}

sub metrics {
    my $metrics;
    my $ok = eval {
        my $pid = open(my $queue, '-|');
        die "cannot inspect queue" unless defined $pid;
        if (!$pid) {
            open STDERR, '>', '/dev/null' or exit 1;
            $SIG{ALRM} = 'DEFAULT';
            alarm 8;
            exec '/usr/sbin/postqueue', '-j';
            exit 1;
        }
        $metrics = collect($queue, time);
        close $queue or die "queue inspection failed";
        1;
    };
    return "# TYPE postfix_queue_scrape_success gauge\npostfix_queue_scrape_success " . ($ok ? "1\n$metrics" : "0\n");
}

if (@ARGV && $ARGV[0] eq '--once') {
    print metrics();
    exit;
}

my $server = IO::Socket::INET->new(LocalAddr => '0.0.0.0', LocalPort => 9154,
    Listen => 8, ReuseAddr => 1) or die "cannot listen";
$SIG{PIPE} = 'IGNORE';
while (my $client = $server->accept()) {
    eval {
        local $SIG{ALRM} = sub { die "timeout" };
        alarm 10;
        my $request = <$client> // '';
        die "invalid request" if length($request) > 4096;
        my ($status, $body) = ('200 OK', "ok\n");
        if ($request =~ m{^GET /metrics HTTP/1\.[01]\r?\n$}) {
            $body = metrics();
        } elsif ($request !~ m{^GET /healthz HTTP/1\.[01]\r?\n$}) {
            ($status, $body) = ('404 Not Found', "not found\n");
        }
        print $client "HTTP/1.1 $status\r\nContent-Type: text/plain; version=0.0.4\r\nContent-Length: " . length($body) . "\r\nConnection: close\r\n\r\n$body";
        alarm 0;
    };
    alarm 0;
    close $client;
}

#!/usr/bin/perl
use strict;
use warnings;
use JSON::PP qw(decode_json);

# Never inspect bodies or log mail headers, recipients, or command errors.
sub candidate {
    my ($record, $now) = @_;
    return 0 unless ($record->{queue_name} // '') eq 'deferred';
    return 0 unless ($record->{queue_id} // '') =~ /\A[A-Za-z0-9]+\z/;
    return 0 unless ($record->{sender} // '') eq 'notifications@andreybondarenko.com';
    return 0 unless ($record->{arrival_time} // '') =~ /\A[0-9]+\z/;
    return $now - $record->{arrival_time} >= 7200;
}

sub confirmation {
    my ($headers) = @_;
    $headers =~ s/\r\n/\n/g;
    $headers =~ s/\n[ \t]+/ /g;
    my @from = $headers =~ /^From:[ \t]*(.*)$/gmi;
    my @subject = $headers =~ /^Subject:[ \t]*(.*)$/gmi;
    return 0 unless @from == 1 && @subject == 1;
    return $from[0] =~ /\Anotifications\@andreybondarenko\.com[ \t]*\z/i
        && $subject[0] =~ /\AMastodon: Confirmation instructions for mastodon\.andreybondarenko\.com[ \t]*\z/;
}

sub capture {
    my (@command) = @_;
    my $pid = open(my $output, '-|');
    die "command unavailable\n" unless defined $pid;
    if (!$pid) {
        open STDERR, '>', '/dev/null' or exit 1;
        exec '/usr/bin/timeout', '15', @command;
        exit 1;
    }
    local $/;
    my $data = <$output> // '';
    my $ok = close $output;
    return $ok ? $data : undef;
}

sub snapshot {
    my $data = capture('/usr/sbin/postqueue', '-j');
    die "queue inspection failed\n" unless defined $data;
    return map { decode_json($_) } grep { length } split /\n/, $data;
}

sub sweep {
    my ($dry_run) = @_;
    my @queue = snapshot();
    for my $record (@queue) {
        next unless candidate($record, time);
        my $id = $record->{queue_id};
        my $headers = capture('/usr/sbin/postcat', '-qh', $id);
        next unless defined($headers) && confirmation($headers);
        # Revalidate after reading headers; queue entries can move or disappear.
        my @current = grep { $_->{queue_id} eq $id } snapshot();
        next unless @current == 1 && candidate($current[0], time)
            && $current[0]->{arrival_time} == $record->{arrival_time};
        if ($dry_run) {
            print "mastodon_confirmation_expiry eligible queue_id=$id\n";
            next;
        }
        # Restrict postsuper to deferred: never delete active or held mail.
        my $result = capture('/usr/sbin/postsuper', '-d', $id, 'deferred');
        print defined($result)
            ? "mastodon_confirmation_expiry processed queue_id=$id\n"
            : "mastodon_confirmation_expiry deletion_failed\n";
    }
}

unless (caller) {
    $| = 1;
    my $dry_run = @ARGV && $ARGV[0] eq '--dry-run';
    while (1) {
        eval { sweep($dry_run); 1 } or print "mastodon_confirmation_expiry inspection_failed\n";
        last if $dry_run;
        sleep 60;
    }
}
1;

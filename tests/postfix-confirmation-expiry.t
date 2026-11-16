use strict;
use warnings;
use JSON::PP;
my $checks = 0;
sub ok { my ($value, $name) = @_; die "FAIL: $name\n" unless $value; $checks++; }
sub is { my ($got, $want, $name) = @_; ok($got eq $want, $name); }
sub is_deeply { my ($got, $want, $name) = @_; ok(encode_json($got) eq encode_json($want), $name); }
sub unlike { my ($got, $pattern, $name) = @_; ok($got !~ $pattern, $name); }
sub done_testing { print "$checks checks passed\n"; }
require "./tools/mail/expire_mastodon_confirmations.pl";
my $record = {queue_name => 'deferred', queue_id => '593EC28',
    sender => 'notifications@andreybondarenko.com', arrival_time => 1000};
ok(!candidate($record, 8199), 'keep mail before two hours');
ok(candidate($record, 8200), 'eligible at exactly two hours');
for my $change (
    {queue_name => 'active'}, {queue_name => 'hold'},
    {sender => 'other@example.org'}, {arrival_time => 'invalid'},
    {queue_id => '../deferred'}, {arrival_time => 9000}
) {
    ok(!candidate({%$record, %$change}, 8200), 'exclude unrelated or unsafe entry');
}
my $headers = "From: notifications\@andreybondarenko.com\nSubject: Mastodon: Confirmation instructions for mastodon.andreybondarenko.com\n";
ok(confirmation($headers), 'recognize exact confirmation');
(my $folded = $headers) =~ s/ for /\n for /;
ok(confirmation($folded), 'recognize folded subject');
for my $change (
    "From: attacker\@example.org\nSubject: Mastodon: Confirmation instructions for mastodon.andreybondarenko.com\n",
    "From: notifications\@andreybondarenko.com\nSubject: Mastodon: Reset password instructions\n",
    $headers . "Subject: duplicate\n", $headers . "From: duplicate\n",
    $headers =~ s/mastodon\.andreybondarenko\.com/other.example.org/r,
) {
    ok(!confirmation($change), 'preserve other message types and ambiguous headers');
}
# Exercise the full sweep without running any external command.
my @commands;
{
    no warnings 'redefine';
    local *main::snapshot = sub { return {%$record}; };
    local *main::capture = sub {
        push @commands, [@_];
        return $headers if $_[0] eq '/usr/sbin/postcat';
        return '' if $_[0] eq '/usr/sbin/postsuper';
        die 'unexpected command';
    };
    local *main::candidate = sub { return 1; };
    my $log = '';
    open my $sink, '>', \$log or die $!;
    local *STDOUT = $sink;
    sweep(1);
    is(scalar(@commands), 1, 'dry run only reads headers');
    @commands = ();
    sweep(0);
    is_deeply($commands[1], ['/usr/sbin/postsuper', '-d', '593EC28', 'deferred'],
        'deletion is confined to deferred queue');
    unlike($log, qr/notifications\@|Confirmation instructions/, 'logs omit mail content');
    @commands = ();
    local *main::snapshot = sub { return (); };
    sweep(0);
    is(scalar(@commands), 0, 'empty snapshot causes no command');
}
done_testing();

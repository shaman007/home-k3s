<?php
/** Read-only web readiness, including maintenance/schema status. No app bootstrap. */
declare(strict_types=1);

function nextcloudJobReady(mixed $value): bool
{
    return is_array($value)
        && ($value['installed'] ?? null) === true
        && ($value['maintenance'] ?? null) === false
        && ($value['needsDbUpgrade'] ?? null) === false;
}

if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) {
    ini_set('display_errors', '0');
    ini_set('log_errors', '0');
    try {
        $context = stream_context_create(['http' => [
            'timeout' => 4,
            'follow_location' => 0,
            'ignore_errors' => true,
            'header' => "Host: cloud.andreybondarenko.com\r\nConnection: close\r\n",
        ]]);
        $body = @file_get_contents(
            'http://nginx-nextcloud.nextcloud.svc.cluster.local:8080/status.php',
            false, $context, 0, 65537
        );
        $status = $http_response_header[0] ?? '';
        if (!preg_match('/^HTTP\/\S+ 200(?: |$)/D', $status)
            || !is_string($body) || strlen($body) > 65536) {
            exit(1);
        }
        exit(nextcloudJobReady(json_decode($body, true, 32, JSON_THROW_ON_ERROR)) ? 0 : 1);
    } catch (Throwable) {
        exit(1);
    }
}

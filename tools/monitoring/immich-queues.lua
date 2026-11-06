-- BullMQ storage names verified against the installed Immich queue inventory.
-- Count containers only; never read job hashes, payloads or failure messages.
local queues = {'thumbnailGeneration', 'metadataExtraction', 'videoConversion',
  'faceDetection', 'facialRecognition', 'smartSearch', 'duplicateDetection',
  'backgroundTask', 'storageTemplateMigration', 'migration', 'search', 'sidecar',
  'library', 'notifications', 'backupDatabase', 'ocr', 'workflow', 'integrityCheck', 'editor'}
local result = {}
local function emit(queue, state, value)
  table.insert(result, 'immich_queue_' .. queue .. '_' .. state)
  table.insert(result, tostring(value))
end
for _, queue in ipairs(queues) do
  local prefix = 'immich_bull:' .. queue .. ':'
  if redis.call('EXISTS', prefix .. 'meta') ~= 1 then error('missing queue metadata') end
  -- BullMQ wait includes a legacy deprecated priority marker; do not count it.
  local waiting = redis.call('LLEN', prefix .. 'wait')
  if redis.call('LINDEX', prefix .. 'wait', -1) == '0:0' then waiting = waiting - 1 end
  emit(queue, 'waiting', waiting + redis.call('ZCARD', prefix .. 'prioritized'))
  for _, state in ipairs({'active', 'paused'}) do
    emit(queue, state, redis.call('LLEN', prefix .. state))
  end
  for _, state in ipairs({'failed', 'delayed'}) do
    emit(queue, state, redis.call('ZCARD', prefix .. state))
  end
end
return result

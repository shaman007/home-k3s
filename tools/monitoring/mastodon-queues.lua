-- Executed with EVAL_RO. Fixed queues cover empty installations; add discovered
-- Sidekiq queues without ever exporting a job body or an argument.
local result = {}
local queues = {default=true, ingress=true, scheduler=true, pull=true, push=true, mailers=true}
for _, name in ipairs(redis.call('SMEMBERS', 'queues')) do
  if string.match(name, '^[%w_%-]+$') then queues[name] = true end
end
local function emit(key, value)
  table.insert(result, key)
  table.insert(result, tostring(value))
end
local now = tonumber(redis.call('TIME')[1])
for name, _ in pairs(queues) do
  local key = 'queue:' .. name
  local size = redis.call('LLEN', key)
  emit('mastodon_queue_' .. name .. '_waiting', size)
  local latency = 0
  local tail = redis.call('LINDEX', key, -1)
  if tail then
    local item = cjson.decode(tail)
    local timestamp = tonumber(item.enqueued_at)
    if not timestamp then error('missing enqueue timestamp') end
    -- Sidekiq 7 uses seconds, Sidekiq 8 uses milliseconds.
    if timestamp > 100000000000 then timestamp = timestamp / 1000 end
    latency = math.max(0, now - timestamp)
  end
  emit('mastodon_queue_' .. name .. '_latency_seconds', latency)
end
for _, state in ipairs({'retry', 'dead', 'schedule'}) do
  emit('mastodon_' .. state .. '_jobs', redis.call('ZCARD', state))
end
return result

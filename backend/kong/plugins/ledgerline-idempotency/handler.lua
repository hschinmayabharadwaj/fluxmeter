-- Kong Lua Plugin: Ledgerline Idempotency
-- Provides atomic idempotency checking using Redis SET NX

local redis = require "resty.redis"

local IdempotencyPlugin = {
  PRIORITY = 1000,
  VERSION = "1.0.0",
}

function IdempotencyPlugin:access(conf)
  local correlation_id = kong.request.get_header("X-Correlation-ID")
  
  if not correlation_id then
    return kong.response.exit(400, {
      message = "Missing X-Correlation-ID header"
    })
  end
  
  -- Connect to Redis
  local red = redis:new()
  red:set_timeout(conf.redis_timeout)
  
  local ok, err = red:connect(conf.redis_host, conf.redis_port)
  if not ok then
    kong.log.err("Failed to connect to Redis: ", err)
    -- Fail open for availability
    return
  end
  
  -- Authenticate if password provided
  if conf.redis_password and conf.redis_password ~= "" then
    local res, err = red:auth(conf.redis_password)
    if not res then
      kong.log.err("Failed to authenticate with Redis: ", err)
      return
    end
  end
  
  -- Check idempotency using SET NX (atomic)
  local idem_key = "idem:" .. correlation_id
  local result, err = red:set(idem_key, "processing", "NX", "EX", conf.ttl)
  
  if not result then
    kong.log.err("Redis SET NX failed: ", err)
    return
  end
  
  if result == ngx.null then
    -- Key already exists - duplicate request
    local cached_response, err = red:get("idem_response:" .. correlation_id)
    
    if cached_response and cached_response ~= ngx.null then
      -- Return cached response
      kong.log.info("Idempotency cache hit for: ", correlation_id)
      
      local response_data = cjson.decode(cached_response)
      return kong.response.exit(response_data.status, response_data.body, response_data.headers)
    else
      -- Request still processing
      return kong.response.exit(409, {
        message = "Request already being processed",
        correlation_id = correlation_id
      })
    end
  end
  
  -- Store correlation_id in context for response phase
  kong.ctx.shared.correlation_id = correlation_id
  
  -- Close Redis connection
  local ok, err = red:set_keepalive(conf.redis_keepalive_timeout, conf.redis_keepalive_pool_size)
  if not ok then
    kong.log.err("Failed to set Redis keepalive: ", err)
  end
end

function IdempotencyPlugin:response(conf)
  local correlation_id = kong.ctx.shared.correlation_id
  
  if not correlation_id then
    return
  end
  
  -- Cache successful responses
  local status = kong.response.get_status()
  
  if status >= 200 and status < 300 then
    local body = kong.response.get_raw_body()
    local headers = kong.response.get_headers()
    
    -- Connect to Redis
    local red = redis:new()
    red:set_timeout(conf.redis_timeout)
    
    local ok, err = red:connect(conf.redis_host, conf.redis_port)
    if not ok then
      kong.log.err("Failed to connect to Redis: ", err)
      return
    end
    
    if conf.redis_password and conf.redis_password ~= "" then
      red:auth(conf.redis_password)
    end
    
    -- Store response for idempotency
    local response_data = {
      status = status,
      body = body,
      headers = headers
    }
    
    local response_key = "idem_response:" .. correlation_id
    red:setex(response_key, conf.response_ttl, cjson.encode(response_data))
    
    kong.log.info("Cached response for: ", correlation_id)
    
    red:set_keepalive(conf.redis_keepalive_timeout, conf.redis_keepalive_pool_size)
  end
end

return IdempotencyPlugin

-- Schema for Ledgerline Idempotency Plugin

return {
  name = "ledgerline-idempotency",
  fields = {
    {
      config = {
        type = "record",
        fields = {
          { redis_host = { type = "string", default = "redis", required = true } },
          { redis_port = { type = "number", default = 6379, required = true } },
          { redis_password = { type = "string", required = false } },
          { redis_timeout = { type = "number", default = 2000 } },
          { redis_keepalive_timeout = { type = "number", default = 60000 } },
          { redis_keepalive_pool_size = { type = "number", default = 30 } },
          { ttl = { type = "number", default = 300 } },
          { response_ttl = { type = "number", default = 3600 } },
        },
      },
    },
  },
}

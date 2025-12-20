from jsonrpcserver import method, Result, Success

@method(name="meta.rpc.ping")
def ping() -> Result:
    return Success("pong")

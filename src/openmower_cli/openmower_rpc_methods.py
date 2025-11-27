from jsonrpcserver import method, Result, Success

@method(name="rpc.ping")
def ping() -> Result:
    return Success("pong")

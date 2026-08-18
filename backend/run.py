import uvicorn

if __name__ == "__main__":
    # Long keep-alive so analyze/upload connections are not dropped while waiting on OpenAI/APS.
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8001,
        reload=True,
        timeout_keep_alive=300,
    )

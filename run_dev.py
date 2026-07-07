import uvicorn
import os

if __name__ == "__main__":
    print("Запуск приложения скоринга ДП...")
    # Запуск сервера
    uvicorn.run(
        "app:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True,
        log_level="info"
    )

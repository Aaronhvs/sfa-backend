"""
SFA — Punto de entrada principal
Uso:
  python run.py           → arranca el servidor web
  python run.py --update  → corre el pipeline de datos y sale
  python run.py --demo    → corre el motor SFA con ejemplos y sale
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

def run_server():
    import uvicorn
    print("\n" + "="*55)
    print("🏆  SFA — Stadistic Football Award")
    print("="*55)
    print("🌐  Abriendo en: http://localhost:8000")
    print("📖  Docs API:    http://localhost:8000/docs")
    print("⏹   Detener:     Ctrl + C")
    print("="*55 + "\n")
    uvicorn.run("backend.api.main:app", host="0.0.0.0", port=8000, reload=False, log_level="warning")

def run_update():
    print("\n" + "="*55)
    print("🔄  SFA — Actualizando datos...")
    print("="*55)
    from backend.pipeline import run_pipeline
    run_pipeline()
    print("\n✅  Listo. Arranca el servidor con: python run.py")

def run_demo():
    import runpy
    runpy.run_module("backend.engine.sfa_engine", run_name="__main__")

if __name__ == "__main__":
    if "--update" in sys.argv:
        run_update()
    elif "--demo" in sys.argv:
        run_demo()
    else:
        run_server()

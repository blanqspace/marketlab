#from modules.health.main import run
from shared.config_loader import load_env
from modules.data_fetcher.main import run
def main():
    load_env()

    run()

if __name__ == "__main__":
    main()

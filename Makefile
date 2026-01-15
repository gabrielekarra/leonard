.PHONY: core core-venv ui install install-venv clean help setup-venv

# Default target
help:
	@echo "Lokus - Local-first AI Engine"
	@echo ""
	@echo "Usage:"
	@echo "  make install       Install Python dependencies (using Poetry)"
	@echo "  make setup-venv    Create virtual environment and install dependencies"
	@echo "  make core          Start the Python core server (using Poetry)"
	@echo "  make core-venv     Start the Python core server (using venv)"
	@echo "  make ui            Build the macOS app"
	@echo "  make clean         Clean build artifacts"
	@echo ""

# Install Python dependencies (Poetry)
install:
	cd core && poetry install

# Create virtual environment and install dependencies
setup-venv:
	cd core && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Start the Python core server (Poetry)
core:
	cd core && poetry run uvicorn leonard.main:app --reload --port 7878

# Start the Python core server (venv)
core-venv:
	cd core && .venv/bin/python -m uvicorn leonard.main:app --reload --port 7878

# Build the macOS app
ui:
	cd apps/desktop && xcodebuild -scheme Leonard -configuration Debug build

# Clean build artifacts
clean:
	rm -rf core/.venv core/__pycache__ core/.pytest_cache
	rm -rf apps/desktop/DerivedData apps/desktop/build

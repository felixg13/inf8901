MAIN = document
BUILD_DIR = build
TEX = lualatex
BIB = bibtex
VIEWER = xdg-open
TEX_FLAGS = -output-directory=$(BUILD_DIR) -interaction=nonstopmode

.PHONY: all
all: $(BUILD_DIR)/$(MAIN).pdf

$(BUILD_DIR):
	@mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/$(MAIN).pdf: $(MAIN).tex references.bib titlepage.tex | $(BUILD_DIR)
	@echo "=== Compilation automatique avec latexmk ==="
	@cp references.bib $(BUILD_DIR)/
	latexmk -pdf -lualatex -output-directory=$(BUILD_DIR) -interaction=nonstopmode $(MAIN).tex
	@echo "✅ Compilation terminée : $(BUILD_DIR)/$(MAIN).pdf"

.PHONY: copy
copy: $(BUILD_DIR)/$(MAIN).pdf
	@echo "📋 Copie du PDF dans la racine..."
	cp $(BUILD_DIR)/$(MAIN).pdf .
	@echo "✅ PDF copié : $(MAIN).pdf"

.PHONY: clean
clean:
	rm -rf $(BUILD_DIR)

.PHONY: view
view: $(BUILD_DIR)/$(MAIN).pdf
	$(VIEWER) $(BUILD_DIR)/$(MAIN).pdf &

.PHONY: quick
quick: | $(BUILD_DIR)
	@echo "⚡ Compilation rapide (1 passe)..."
	@cp -f references.bib $(BUILD_DIR)/ 2>/dev/null || true
	$(TEX) $(TEX_FLAGS) $(MAIN).tex
	@echo "✅ Compilation rapide terminée"

.PHONY: help
help:
	@echo "📚 Makefile - Projet LaTeX"
	@echo ""
	@echo "Cibles disponibles:"
	@echo "  make              - Compilation (défaut)"
	@echo "  make quick        - Compilation rapide (1 passe)"
	@echo "  make copy         - Copier le PDF dans la racine"
	@echo "  make clean        - Nettoyer le dossier build"
	@echo "  make view         - Visualiser le PDF"
	@echo "  make help         - Afficher cette aide"

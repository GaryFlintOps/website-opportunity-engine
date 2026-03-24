#!/bin/bash
# ── Website Opportunity Engine — Fresh Git History ────────────────────────────
# The old commit contains a 109MB binary in history.
# This script destroys git history entirely and starts a clean single commit.
#
# Run from your Mac Terminal inside the project folder:
#   cd ~/path/to/website-opportunity-engine
#   bash clean-repo.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

echo "📦 Starting fresh git history..."
echo "Working dir: $(pwd)"

# ── Safety check ──────────────────────────────────────────────────────────────
if [ ! -f "requirements.txt" ]; then
    echo "❌ Run this from inside the website-opportunity-engine folder"
    exit 1
fi

# ── 1. Save remote URL before nuking .git ────────────────────────────────────
REMOTE=$(git remote get-url origin 2>/dev/null || echo "")
if [ -z "$REMOTE" ]; then
    echo "❌ No git remote found. Set one first: git remote add origin <url>"
    exit 1
fi
echo "✓ Remote saved: $REMOTE"

# ── 2. Nuke entire git history ────────────────────────────────────────────────
echo "⏳ Removing old .git directory..."
rm -rf .git
echo "✓ Old history gone"

# ── 3. Fresh init ─────────────────────────────────────────────────────────────
git init -b main
echo "✓ Fresh repo initialised (branch: main)"

# ── 4. Stage only clean files (.gitignore excludes node_modules/venv) ────────
echo "⏳ Staging clean files..."
git add .
echo "✓ Files staged"

# ── 5. Sanity check — node_modules must NOT appear ───────────────────────────
NM_COUNT=$(git diff --cached --name-only | grep -c "node_modules" || true)
if [ "$NM_COUNT" -gt 0 ]; then
    echo "❌ node_modules still staged ($NM_COUNT files). Check .gitignore"
    exit 1
fi
echo "✓ node_modules not staged (confirmed clean)"

# ── 6. Show what's going in ───────────────────────────────────────────────────
echo ""
echo "Files being committed:"
git diff --cached --stat | tail -10
echo ""

# ── 7. Initial commit ────────────────────────────────────────────────────────
git commit -m "init: clean repo — node_modules and venv excluded"
echo "✓ Clean commit created"

# ── 8. Re-attach remote and force push ───────────────────────────────────────
git remote add origin "$REMOTE"
echo "⏳ Force pushing to $REMOTE ..."
git push origin main --force
echo "✓ Force push complete"

# ── 9. Final stats ───────────────────────────────────────────────────────────
echo ""
echo "📊 Repo stats:"
git count-objects -vH
echo ""
echo "✅ Done. Clean single-commit history pushed to GitHub."
echo "   No node_modules. No venv. No large binaries."
echo "   GitHub will accept all future pushes."

# Pre-commit Setup for Pokemon Project

This project uses pre-commit hooks to automatically run linting and sanity tests before each commit, ensuring code quality and that apps work as users expect.

## Quick Setup

1. **Install dependencies and hooks:**
   ```bash
   python setup_pre_commit.py
   ```

2. **Test the setup:**
   ```bash
   python run_pre_commit_checks.py
   ```

3. **Make a test commit:**
   ```bash
   git add .
   git commit -m "Test pre-commit hooks"
   ```

## What Gets Checked

### Before Every Commit
- **Pokemon Linter** - Runs `python lint.py --lint-only` (ruff linting)
- **Pokemon App Validation** - Runs `python lint.py --apps-only` (app structure)
- **Pokemon Sanity Tests** - Runs `python lint.py --sanity` (user experience tests)
- **Code Formatting** - Ruff formatter and Black for notebooks
- **Basic Quality** - Trailing whitespace, file endings, JSON validation

### Smart Filtering
- Linter runs on all `.py` files
- App validation only runs when `src/apps/*.py` files change
- Sanity tests run when `src/`, `tests/`, or `lint.py` files change
- Large files (>10MB) are blocked
- Merge conflicts are detected

## Manual Testing

### Run All Checks
```bash
# Run everything that would run on commit
python run_pre_commit_checks.py

# Run with detailed output  
python run_pre_commit_checks.py --verbose
```

### Run Specific Checks
```bash
# Just the linter
python run_pre_commit_checks.py --hook linter

# Just app validation
python run_pre_commit_checks.py --hook apps

# Just sanity tests
python run_pre_commit_checks.py --hook sanity

# Just ruff checks
python run_pre_commit_checks.py --hook ruff
```

### Run on Staged Files Only
```bash
python run_pre_commit_checks.py --files
```

## Direct Commands

### Pre-commit Framework
```bash
# Run all hooks manually
pre-commit run --all-files

# Run specific hook
pre-commit run pokemon-sanity-tests

# Update hook versions
pre-commit autoupdate

# Install hooks after cloning
pre-commit install
```

### Pokemon-Specific Commands
```bash
# Full lint and validation
python lint.py

# Just linting (fast)
python lint.py --lint-only  

# Just app validation
python lint.py --apps-only

# Comprehensive sanity tests
python lint.py --sanity

# Comprehensive sanity tests with details
python tests/sanity_test_runner.py --details
```

## Skipping Hooks

### Skip All Hooks (Emergency)
```bash
git commit --no-verify -m "Emergency fix"
```

### Skip Specific Hook
```bash
SKIP=pokemon-sanity-tests git commit -m "Skip slow tests"
```

### Skip Multiple Hooks
```bash
SKIP=pokemon-sanity-tests,pokemon-linter git commit -m "Skip tests and linter"
```

## Troubleshooting

### Camera Tests Fail in CI
Camera tests are automatically skipped in pre-commit/CI environments. If they're still failing, set:
```bash
export PRE_COMMIT=1
```

### Memory Tests Fail
If memory tests are unreliable, they can be disabled in `tests/pre_commit_configuration.py`:
```python
"skip_memory_tests": True,
```

### Tests Are Too Slow
Enable quick mode permanently:
```python
"use_quick_mode": True,
```

### Hook Installation Issues
```bash
# Reinstall hooks
pre-commit uninstall
pre-commit install

# Clean and reinstall
pre-commit clean
pre-commit install --install-hooks
```

## CI Integration

The pre-commit configuration includes `pre-commit.ci` integration for automatic updates and fixing in pull requests.

## File Structure

```
.pre-commit-config.yaml     # Pre-commit configuration
setup_pre_commit.py         # One-time setup script
run_pre_commit_checks.py    # Manual testing script
tests/pre_commit_configuration.py  # Environment detection
```

## Performance

- **Linting**: ~2-5 seconds
- **App Validation**: ~3-8 seconds  
- **Sanity Tests**: ~15-30 seconds (quick mode)
- **Total**: ~20-45 seconds per commit

The hooks are designed to be fast enough for regular development while providing comprehensive validation.

# Gmail Organizer

Automatically organize your Gmail inbox using configurable YAML rules. Label, archive, star, or delete emails based on sender, subject, body, or attachment status.

## Setup

### 1. Google Cloud Credentials

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable the **Gmail API**
3. Create OAuth 2.0 credentials (Desktop application)
4. Download the credentials JSON and save it as `config/credentials.json`

### 2. Install

```bash
cd gmail-organizer
pip install -e ".[dev]"
```

### 3. Configure Rules

```bash
cp config/rules.example.yaml config/rules.yaml
# Edit rules.yaml with your own rules
```

## Usage

```bash
# Preview what would happen (no changes made)
gmail-organizer --dry-run

# Run the organizer
gmail-organizer

# Use custom rules file
gmail-organizer --rules my-rules.yaml

# Verbose output
gmail-organizer -v
```

## Writing Rules

Rules are defined in YAML. Each rule has:
- **name**: A descriptive name
- **match_field**: What to match (`from`, `to`, `subject`, `body`, `has_attachment`)
- **pattern**: Regex pattern to match against
- **actions**: List of actions (`label`, `archive`, `mark_read`, `star`, `delete`)
- **target_label**: Required when using the `label` action
- **enabled**: Set to `false` to skip a rule (default: `true`)

See `config/rules.example.yaml` for examples.

## Testing

```bash
pytest -v
```

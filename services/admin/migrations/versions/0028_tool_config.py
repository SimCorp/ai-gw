"""Create tool_config table and seed from catalog"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TOOLS = [
    ("hash-text", "Hash text", "Crypto"),
    ("hmac-generator", "HMAC generator", "Crypto"),
    ("rsa-key-pair-generator", "RSA key pair generator", "Crypto"),
    ("password-strength-analyser", "Password strength analyser", "Crypto"),
    ("bcrypt", "Bcrypt", "Crypto"),
    ("uuid-generator", "UUID generator", "Crypto"),
    ("ulid-generator", "ULID generator", "Crypto"),
    ("token-generator", "Token generator", "Crypto"),
    ("base64-string-converter", "Base64 string encoder/decoder", "Converter"),
    ("base64-file-converter", "Base64 file converter", "Converter"),
    ("color-converter", "Color converter", "Converter"),
    ("case-converter", "Case converter", "Converter"),
    ("roman-numeral-converter", "Roman numeral converter", "Converter"),
    ("base-converter", "Integer base converter", "Converter"),
    ("ascii-converter", "ASCII/text converter", "Converter"),
    ("yaml-to-json-converter", "YAML to JSON", "Converter"),
    ("json-to-yaml-converter", "JSON to YAML", "Converter"),
    ("xml-to-json-converter", "XML to JSON", "Converter"),
    ("markdown-to-html", "Markdown to HTML", "Converter"),
    ("toml-to-json", "TOML to JSON", "Converter"),
    ("json-to-csv", "JSON to CSV", "Converter"),
    ("csv-to-json", "CSV to JSON", "Converter"),
    ("url-encoder", "URL encoder/decoder", "Web"),
    ("html-entities", "HTML entities encoder/decoder", "Web"),
    ("url-parser", "URL parser", "Web"),
    ("device-information", "Device information", "Web"),
    ("basic-auth-generator", "Basic auth generator", "Web"),
    ("meta-tag-generator", "Meta tag generator", "Web"),
    ("og-meta-generator", "OG meta tag generator", "Web"),
    ("http-status-codes", "HTTP status codes", "Web"),
    ("mime-types", "MIME types", "Web"),
    ("jwt-parser", "JWT parser", "Web"),
    ("keycode-info", "Keycode info", "Web"),
    ("qr-code-generator", "QR code generator", "Images & Videos"),
    ("wifi-qr-code-generator", "Wi-Fi QR code generator", "Images & Videos"),
    ("svg-placeholder-generator", "SVG placeholder generator", "Images & Videos"),
    ("image-compressor", "Image compressor", "Images & Videos"),
    ("camera-recorder", "Camera recorder", "Images & Videos"),
    ("color-picker", "Color picker", "Images & Videos"),
    ("exif-viewer", "EXIF viewer", "Images & Videos"),
    ("png-to-jpeg-converter", "PNG to JPEG converter", "Images & Videos"),
    ("json-formatter", "JSON formatter", "Development"),
    ("json-minify", "JSON minifier", "Development"),
    ("json-diff", "JSON diff", "Development"),
    ("json-editor", "JSON editor", "Development"),
    ("javascript-minifier", "JavaScript minifier", "Development"),
    ("html-minifier", "HTML minifier", "Development"),
    ("css-minifier", "CSS minifier", "Development"),
    ("regex-tester", "Regex tester", "Development"),
    ("prettier", "Prettier formatter", "Development"),
    ("docker-run-to-docker-compose-converter", "Docker run to Compose", "Development"),
    ("sql-formatter", "SQL formatter", "Development"),
    ("crontab-generator", "Cron expression generator", "Development"),
    ("git-memo", "Git cheatsheet", "Development"),
    ("css-specificity-calculator", "CSS specificity calculator", "Development"),
    ("ip-subnet-calculator", "IPv4 subnet calculator", "Network"),
    ("ip-address-converter", "IP address converter", "Network"),
    ("ipv4-range-expander", "IPv4 range expander", "Network"),
    ("ipv4-cidr", "IPv4 CIDR converter", "Network"),
    ("mac-address-generator", "MAC address generator", "Network"),
    ("user-agent-parser", "User-agent parser", "Network"),
    ("port-list", "Common port list", "Network"),
    ("math-evaluator", "Math expression evaluator", "Math"),
    ("eta-calculator", "ETA calculator", "Math"),
    ("percentage-calculator", "Percentage calculator", "Math"),
    ("average-calculator", "Average calculator", "Math"),
    ("prime-factorisation", "Prime factorisation", "Math"),
    ("temperature-converter", "Temperature converter", "Measurement"),
    ("byte-converter", "Byte converter", "Measurement"),
    ("length-converter", "Length converter", "Measurement"),
    ("weight-converter", "Weight converter", "Measurement"),
    ("speed-converter", "Speed converter", "Measurement"),
    ("area-converter", "Area converter", "Measurement"),
    ("pressure-converter", "Pressure converter", "Measurement"),
    ("text-statistics", "Text statistics", "Text"),
    ("lorem-ipsum-generator", "Lorem ipsum generator", "Text"),
    ("text-diff", "Text diff", "Text"),
    ("numeronym-generator", "Numeronym generator", "Text"),
    ("text-to-nato-alphabet", "NATO phonetic alphabet", "Text"),
    ("emoji-picker", "Emoji picker", "Text"),
    ("string-obfuscator", "String obfuscator", "Text"),
    ("slugify-string", "Slugify string", "Text"),
    ("phone-parser", "Phone number parser", "Data"),
    ("iban-validator-and-parser", "IBAN validator", "Data"),
    ("chronometer", "Chronometer", "Data"),
    ("date-time-converter", "Date-time converter", "Time & Date"),
    ("unix-timestamp-converter", "Unix timestamp converter", "Time & Date"),
    ("cron-parser", "Cron expression parser", "Time & Date"),
    ("timezone-converter", "Timezone converter", "Time & Date"),
    ("age-calculator", "Age calculator", "Time & Date"),
    ("random-port-generator", "Random port generator", "Random"),
    ("password-generator", "Password generator", "Random"),
    ("random-string", "Random string generator", "Random"),
    ("dice-roller", "Dice roller", "Random"),
    ("coin-flip", "Coin flip", "Random"),
    ("random-number-generator", "Random number generator", "Random"),
]


def upgrade():
    op.create_table(
        "tool_config",
        sa.Column("tool_id", sa.Text, primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            INSERT INTO tool_config (tool_id, label, category, enabled)
            VALUES (:tool_id, :label, :category, true)
            ON CONFLICT (tool_id) DO NOTHING
        """),
        [{"tool_id": tid, "label": lbl, "category": cat} for tid, lbl, cat in _TOOLS],
    )


def downgrade():
    op.drop_table("tool_config")

import datetime
import ipaddress
import os
import socket
from pathlib import Path
from typing import Tuple

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from app.core.config import DATA_DIR
from app.core.logger import get_logger

logger = get_logger("IssueSlipApp.CertManager")


def get_local_ip() -> str:
    """Detect LAN IPv4 address of the host machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def ensure_certificate(ip_address: str = "") -> Tuple[Path, Path]:
    """
    Ensure a self-signed TLS/HTTPS certificate exists for the current LAN IP.
    Returns (cert_path, key_path).
    """
    if not ip_address:
        ip_address = get_local_ip()

    cert_dir = DATA_DIR / "certs"
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_file = cert_dir / "cert.pem"
    key_file = cert_dir / "key.pem"

    # Check if existing certificate is valid and covers current IP
    if cert_file.exists() and key_file.exists():
        try:
            with open(cert_file, "rb") as f:
                cert_data = f.read()
            cert = x509.load_pem_x509_certificate(cert_data)
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            expiry = getattr(cert, "not_valid_after_utc", None)
            if expiry is None:
                expiry = cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)
            if expiry > now_utc + datetime.timedelta(days=30):
                # Check SAN covers current IP
                san_ext = cert.extensions.get_extension_for_oid(x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                ip_covered = any(
                    str(ip) == ip_address
                    for ip in san_ext.value.get_values_for_type(x509.IPAddress)
                )
                if ip_covered:
                    logger.info(f"Existing TLS certificate valid for IP: {ip_address}")
                    return cert_file, key_file
        except Exception as exc:
            logger.warning(f"Existing certificate check failed ({exc}), regenerating...")

    logger.info(f"Generating new self-signed TLS certificate for LAN IP: {ip_address}")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Telangana"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Hyderabad"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "TIME TECHNO PLAST"),
        x509.NameAttribute(NameOID.COMMON_NAME, f"TTL-Scanner-{ip_address}")
    ])

    san_items = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))
    ]
    try:
        san_items.append(x509.IPAddress(ipaddress.IPv4Address(ip_address)))
    except Exception:
        pass

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))  # 10 years
        .add_extension(x509.SubjectAlternativeName(san_items), critical=False)
        .sign(key, hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )

    with open(cert_file, "wb") as f:
        f.write(cert_pem)
    with open(key_file, "wb") as f:
        f.write(key_pem)

    logger.info(f"Saved TLS certificate to {cert_file} and key to {key_file}")
    return cert_file, key_file

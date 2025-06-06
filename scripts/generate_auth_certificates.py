#!/usr/bin/env python3
"""
Script to generate certificates for a CA, server, and client allowing for
client authentication using mTLS certificates. This can then be used to test
mTLS client authentication for Redfish and WebUI.
"""

import argparse
import datetime
import errno
import ipaddress
import os
import socket
import time
from typing import Optional

import asn1
import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    pkcs12,
)
from cryptography.x509.oid import NameOID

replaceCertPath = "/redfish/v1/CertificateService/Actions/CertificateService.ReplaceCertificate"
# https://oidref.com/1.3.6.1.4.1.311.20.2.3
upnObjectIdentifier = "1.3.6.1.4.1.311.20.2.3"


class RedfishSessionContext:
    def __init__(self, client, username="root", password="0penBmc"):
        self.client = client
        self.session_uri = None
        self.x_auth_token = None
        self.username = username
        self.password = password

    def __enter__(self):
        r = self.client.post(
            "/redfish/v1/SessionService/Sessions",
            json={
                "UserName": self.username,
                "Password": self.password,
                "Context": f"pythonscript::{os.path.basename(__file__)}",
            },
            headers={"content-type": "application/json"},
        )
        r.raise_for_status()
        self.x_auth_token = r.headers["x-auth-token"]
        self.session_uri = r.headers["location"]
        return self

    def __exit__(self, type, value, traceback):
        if not self.session_uri:
            return
        r = self.client.delete(self.session_uri)
        r.raise_for_status()


def get_hostname(redfish_session, username, password, url):
    service_root = redfish_session.get("/redfish/v1/")
    service_root.raise_for_status()

    manager_uri = service_root.json()["Links"]["ManagerProvidingService"][
        "@odata.id"
    ]

    manager_response = redfish_session.get(manager_uri)
    manager_response.raise_for_status()

    network_protocol_uri = manager_response.json()["NetworkProtocol"][
        "@odata.id"
    ]

    network_protocol_response = redfish_session.get(network_protocol_uri)
    network_protocol_response.raise_for_status()

    hostname = network_protocol_response.json()["HostName"]

    return hostname


def generateCA():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    builder = x509.CertificateBuilder()

    name = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OpenBMC"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "bmcweb"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Test CA"),
        ]
    )
    builder = builder.subject_name(name)
    builder = builder.issuer_name(name)

    builder = builder.not_valid_before(
        datetime.datetime(1970, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
    )
    builder = builder.not_valid_after(
        datetime.datetime(2070, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
    )
    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.public_key(public_key)

    basic_constraints = x509.BasicConstraints(ca=True, path_length=None)
    builder = builder.add_extension(basic_constraints, critical=True)

    usage = x509.KeyUsage(
        content_commitment=False,
        crl_sign=True,
        data_encipherment=False,
        decipher_only=False,
        digital_signature=False,
        encipher_only=False,
        key_agreement=False,
        key_cert_sign=True,
        key_encipherment=False,
    )
    builder = builder.add_extension(usage, critical=False)

    auth_key = x509.AuthorityKeyIdentifier.from_issuer_public_key(public_key)

    builder = builder.add_extension(auth_key, critical=False)

    root_cert = builder.sign(
        private_key=private_key, algorithm=hashes.SHA256()
    )

    return private_key, root_cert


def signCsr(csr, ca_key):
    csr.sign(ca_key, algorithm=hashes.SHA256())
    return


def generate_client_key_and_cert(
    ca_cert,
    ca_key,
    common_name: Optional[str] = None,
    upn: Optional[str] = None,
):
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    builder = x509.CertificateBuilder()

    cert_names = [
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OpenBMC"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "bmcweb"),
    ]
    if common_name is not None:
        cert_names.append(x509.NameAttribute(NameOID.COMMON_NAME, common_name))

    builder = builder.subject_name(x509.Name(cert_names))

    builder = builder.issuer_name(ca_cert.subject)
    builder = builder.public_key(public_key)
    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.not_valid_before(
        datetime.datetime(1970, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
    )
    builder = builder.not_valid_after(
        datetime.datetime(2070, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
    )

    usage = x509.KeyUsage(
        content_commitment=False,
        crl_sign=False,
        data_encipherment=False,
        decipher_only=False,
        digital_signature=True,
        encipher_only=False,
        key_agreement=True,
        key_cert_sign=False,
        key_encipherment=False,
    )
    builder = builder.add_extension(usage, critical=False)

    exusage = x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH])
    builder = builder.add_extension(exusage, critical=True)

    auth_key = x509.AuthorityKeyIdentifier.from_issuer_public_key(public_key)
    builder = builder.add_extension(auth_key, critical=False)

    if upn is not None:
        encoder = asn1.Encoder()
        encoder.start()
        encoder.write(upn, asn1.Numbers.UTF8String)

        builder = builder.add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.OtherName(
                        x509.ObjectIdentifier(upnObjectIdentifier),
                        encoder.output(),
                    )
                ]
            ),
            critical=False,
        )

    signed = builder.sign(private_key=ca_key, algorithm=hashes.SHA256())

    return private_key, signed


def generateServerCert(url, ca_key, ca_cert, csr):
    builder = x509.CertificateBuilder()

    builder = builder.subject_name(csr.subject)
    builder = builder.issuer_name(ca_cert.subject)
    builder = builder.public_key(csr.public_key())
    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.not_valid_before(
        datetime.datetime(1970, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
    )
    builder = builder.not_valid_after(
        datetime.datetime(2070, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
    )

    usage = x509.KeyUsage(
        content_commitment=False,
        crl_sign=False,
        data_encipherment=False,
        decipher_only=False,
        digital_signature=True,
        encipher_only=False,
        key_agreement=False,
        key_cert_sign=True,
        key_encipherment=True,
    )
    builder = builder.add_extension(usage, critical=True)

    exusage = x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH])
    builder = builder.add_extension(exusage, critical=True)

    san_list = [x509.DNSName("localhost")]
    try:
        value = ipaddress.ip_address(url)
        san_list.append(x509.IPAddress(value))
    except ValueError:
        san_list.append(x509.DNSName(url))

    altname = x509.SubjectAlternativeName(san_list)
    builder = builder.add_extension(altname, critical=True)
    basic_constraints = x509.BasicConstraints(ca=False, path_length=None)
    builder = builder.add_extension(basic_constraints, critical=True)

    builder = builder.add_extension(
        x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
        critical=False,
    )
    authkeyident = x509.AuthorityKeyIdentifier.from_issuer_public_key(
        ca_key.public_key()
    )
    builder = builder.add_extension(authkeyident, critical=False)

    signed = builder.sign(private_key=ca_key, algorithm=hashes.SHA256())

    return signed


def generateCsr(
    redfish_session,
    commonName,
    manager_uri,
):
    try:
        socket.inet_aton(commonName)
        commonName = "IP: " + commonName
    except socket.error:
        commonName = "DNS: " + commonName

    CSRRequest = {
        "CommonName": commonName,
        "City": "San Fransisco",
        "Country": "US",
        "Organization": "",
        "OrganizationalUnit": "",
        "State": "CA",
        "CertificateCollection": {
            "@odata.id": f"{manager_uri}/NetworkProtocol/HTTPS/Certificates",
        },
        "AlternativeNames": [
            commonName,
            "DNS: localhost",
            "IP: 127.0.0.1",
        ],
    }

    response = redfish_session.post(
        "/redfish/v1/CertificateService/Actions/CertificateService.GenerateCSR",
        json=CSRRequest,
    )
    response.raise_for_status()

    csrString = response.json()["CSRString"]
    csr = x509.load_pem_x509_csr(csrString.encode())
    if not csr.is_signature_valid:
        raise Exception("CSR was not valid")
    return csr


def install_ca_cert(redfish_session, ca_cert_dump, manager_uri):
    ca_certJSON = {
        "CertificateString": ca_cert_dump.decode(),
        "CertificateType": "PEM",
    }
    ca_certPath = f"{manager_uri}/Truststore/Certificates"
    print("Attempting to install CA certificate to BMC.")

    response = redfish_session.post(ca_certPath, json=ca_certJSON)
    if response.status_code == 500:
        print(
            "An existing CA certificate is likely already installed."
            " Replacing..."
        )
        ca_certJSON["CertificateUri"] = {
            "@odata.id": ca_certPath + "/1",
        }

        response = redfish_session.post(replaceCertPath, json=ca_certJSON)
        if response.status_code == 200:
            print("Successfully replaced existing CA certificate.")
        else:
            raise Exception(
                "Could not install or replace CA certificate."
                "Please check if a certificate is already installed. If a"
                "certificate is already installed, try performing a factory"
                "restore to clear such settings."
            )
    response.raise_for_status()
    print("Successfully installed CA certificate.")


def install_server_cert(redfish_session, manager_uri, server_cert_dump):

    server_cert_json = {
        "CertificateString": server_cert_dump.decode(),
        "CertificateUri": {
            "@odata.id": f"{manager_uri}/NetworkProtocol/HTTPS/Certificates/1",
        },
        "CertificateType": "PEM",
    }

    print("Replacing server certificate...")
    response = redfish_session.post(replaceCertPath, json=server_cert_json)
    if response.status_code == 200:
        print("Successfully replaced server certificate.")
    else:
        raise Exception(f"Could not replace certificate: {response.json()}")

    tls_patch_json = {"Oem": {"OpenBMC": {"AuthMethods": {"TLS": True}}}}
    print("Ensuring TLS authentication is enabled.")
    response = redfish_session.patch(
        "/redfish/v1/AccountService", json=tls_patch_json
    )
    if response.status_code == 200:
        print("Successfully enabled TLS authentication.")
    else:
        raise Exception("Could not enable TLS auth: " + response.read)


def generate_pk12(certs_dir, key, client_cert, username):
    print("Generating p12 cert file for browser authentication.")
    p12 = pkcs12.serialize_key_and_certificates(
        username.encode(),
        key,
        client_cert,
        None,
        serialization.NoEncryption(),
    )
    with open(os.path.join(certs_dir, "client.p12"), "wb") as f:
        f.write(p12)


def test_mtls_auth(url, certs_dir):
    with httpx.Client(
        base_url=f"https://{url}",
        verify=os.path.join(certs_dir, "CA-cert.cer"),
        cert=(
            os.path.join(certs_dir, "client-cert.pem"),
            os.path.join(certs_dir, "client-key.pem"),
        ),
    ) as client:
        print("Testing mTLS auth with CommonName")
        response = client.get(
            "/redfish/v1/SessionService/Sessions",
        )
        response.raise_for_status()

        print("Changing CertificateMappingAttribute to use UPN")
        patch_json = {
            "MultiFactorAuth": {
                "ClientCertificate": {
                    "CertificateMappingAttribute": "UserPrincipalName"
                }
            }
        }
        response = client.patch(
            "/redfish/v1/AccountService",
            json=patch_json,
        )
        response.raise_for_status()

    with httpx.Client(
        base_url=f"https://{url}",
        verify=os.path.join(certs_dir, "CA-cert.cer"),
        cert=(
            os.path.join(certs_dir, "upn-client-cert.pem"),
            os.path.join(certs_dir, "upn-client-key.pem"),
        ),
    ) as client:
        print("Retesting mTLS auth with UPN")
        response = client.get(
            "/redfish/v1/SessionService/Sessions",
        )
        response.raise_for_status()

        print("Changing CertificateMappingAttribute to use CommonName")
        patch_json = {
            "MultiFactorAuth": {
                "ClientCertificate": {
                    "CertificateMappingAttribute": "CommonName"
                }
            }
        }
        response = client.patch(
            "/redfish/v1/AccountService",
            json=patch_json,
        )
        response.raise_for_status()


def setup_server_cert(
    redfish_session,
    ca_cert_dump,
    certs_dir,
    client_key,
    client_cert,
    username,
    url,
    server_intermediate_key,
    server_intermediate_cert,
):
    service_root = redfish_session.get("/redfish/v1/")
    service_root.raise_for_status()

    manager_uri = service_root.json()["Links"]["ManagerProvidingService"][
        "@odata.id"
    ]

    install_ca_cert(redfish_session, ca_cert_dump, manager_uri)
    generate_pk12(certs_dir, client_key, client_cert, username)

    csr = generateCsr(
        redfish_session,
        url,
        manager_uri,
    )
    serverCert = generateServerCert(
        url,
        server_intermediate_key,
        server_intermediate_cert,
        csr,
    )
    server_cert_dump = serverCert.public_bytes(
        encoding=serialization.Encoding.PEM
    )

    # If using intermediate certificate, save server cert without intermediate for debugging
    if (
        isinstance(server_intermediate_cert, x509.Certificate)
        and server_intermediate_cert.subject != server_intermediate_cert.issuer
    ):
        with open(os.path.join(certs_dir, "server-cert-only.pem"), "wb") as f:
            f.write(server_cert_dump)
            print("Server cert (without intermediate) saved for debugging.")
        intermediate_cert_dump = server_intermediate_cert.public_bytes(
            encoding=serialization.Encoding.PEM
        )
        server_cert_dump = server_cert_dump + intermediate_cert_dump

    with open(os.path.join(certs_dir, "server-cert.pem"), "wb") as f:
        f.write(server_cert_dump)
        print("Server cert generated.")

    install_server_cert(redfish_session, manager_uri, server_cert_dump)

    print("Make sure setting CertificateMappingAttribute to CommonName")
    patch_json = {
        "MultiFactorAuth": {
            "ClientCertificate": {"CertificateMappingAttribute": "CommonName"}
        }
    }
    response = redfish_session.patch(
        "/redfish/v1/AccountService", json=patch_json
    )
    response.raise_for_status()


def generateIntermediateCA(ca_key, ca_cert, name_prefix):
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    builder = x509.CertificateBuilder()

    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Santa Clara"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OpenBMC"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "bmcweb"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Test Intermediate"),
        ]
    )
    builder = builder.subject_name(name)
    builder = builder.issuer_name(ca_cert.subject)

    builder = builder.not_valid_before(
        datetime.datetime(1970, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
    )
    builder = builder.not_valid_after(
        datetime.datetime(2070, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
    )

    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.public_key(public_key)

    basic_constraints = x509.BasicConstraints(ca=True, path_length=0)
    builder = builder.add_extension(basic_constraints, critical=True)

    usage = x509.KeyUsage(
        content_commitment=False,
        crl_sign=True,
        data_encipherment=False,
        decipher_only=False,
        digital_signature=False,
        encipher_only=False,
        key_agreement=False,
        key_cert_sign=True,
        key_encipherment=False,
    )
    builder = builder.add_extension(usage, critical=True)

    auth_key = x509.AuthorityKeyIdentifier.from_issuer_public_key(public_key)
    builder = builder.add_extension(auth_key, critical=False)

    intermediate_cert = builder.sign(
        private_key=ca_key, algorithm=hashes.SHA256()
    )

    return private_key, intermediate_cert


def generate_and_load_certs(url, username, password, use_intermediate=False):
    certs_dir = os.path.expanduser("~/certs")
    print(f"Writing certs to {certs_dir}")
    try:
        print("Making certs directory.")
        os.mkdir(certs_dir)
    except OSError as error:
        if error.errno != errno.EEXIST:
            raise

    ca_cert_filename = os.path.join(certs_dir, "CA-cert.cer")
    ca_key_filename = os.path.join(certs_dir, "CA-key.pem")
    if not os.path.exists(ca_cert_filename):
        ca_key, ca_cert = generateCA()

        ca_key_dump = ca_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        ca_cert_dump = ca_cert.public_bytes(
            encoding=serialization.Encoding.PEM
        )

        with open(ca_cert_filename, "wb") as f:
            f.write(ca_cert_dump)
            print("CA cert generated.")
        with open(ca_key_filename, "wb") as f:
            f.write(ca_key_dump)
            print("CA key generated.")

    with open(ca_cert_filename, "rb") as ca_cert_file:
        ca_cert_dump = ca_cert_file.read()
    ca_cert = x509.load_pem_x509_certificate(ca_cert_dump)

    with open(ca_key_filename, "rb") as ca_key_file:
        ca_key_dump = ca_key_file.read()
    ca_key = load_pem_private_key(ca_key_dump, None)

    # Generate intermediate certificates if requested
    if use_intermediate:
        # Generate client intermediate
        client_intermediate_key, client_intermediate_cert = (
            generateIntermediateCA(ca_key, ca_cert, "client")
        )
        # ... save client intermediate certs ...

        # Generate server intermediate
        server_intermediate_key, server_intermediate_cert = (
            generateIntermediateCA(ca_key, ca_cert, "server")
        )
    else:
        client_intermediate_key = ca_key
        client_intermediate_cert = ca_cert
        server_intermediate_key = ca_key
        server_intermediate_cert = ca_cert

    # Update client cert generation to use intermediate
    client_key, client_cert = generate_client_key_and_cert(
        ca_cert=client_intermediate_cert,
        ca_key=client_intermediate_key,
        common_name=username,
    )
    client_key_dump = client_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    with open(os.path.join(certs_dir, "client-key.pem"), "wb") as f:
        f.write(client_key_dump)
        print("Client key generated.")
    client_cert_dump = client_cert.public_bytes(
        encoding=serialization.Encoding.PEM
    )

    # Save client certificate without intermediate for debugging
    if use_intermediate:
        with open(os.path.join(certs_dir, "client-cert-only.pem"), "wb") as f:
            f.write(client_cert_dump)
            print("Client cert (without intermediate) saved for debugging.")
        client_cert_dump = (
            client_cert_dump
            + client_intermediate_cert.public_bytes(
                encoding=serialization.Encoding.PEM
            )
        )  # Append intermediate to create chain

    with open(os.path.join(certs_dir, "client-cert.pem"), "wb") as f:
        f.write(client_cert_dump)
        print("Client cert generated.")

    print(f"Connecting to {url}")
    with httpx.Client(
        base_url=f"https://{url}", verify=False, follow_redirects=False
    ) as redfish_session:
        with RedfishSessionContext(
            redfish_session, username, password
        ) as rf_session:
            redfish_session.headers["X-Auth-Token"] = rf_session.x_auth_token

            hostname = get_hostname(redfish_session, username, password, url)
            print(f"Hostname: {hostname}")

            upn_client_key, upn_client_cert = generate_client_key_and_cert(
                ca_cert,
                ca_key,
                upn=f"{username}@{hostname}",
            )
            upn_client_key_dump = upn_client_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
            with open(
                os.path.join(certs_dir, "upn-client-key.pem"), "wb"
            ) as f:
                f.write(upn_client_key_dump)
                print("UPN client key generated.")

            upn_client_cert_dump = upn_client_cert.public_bytes(
                encoding=serialization.Encoding.PEM
            )
            with open(
                os.path.join(certs_dir, "upn-client-cert.pem"), "wb"
            ) as f:
                f.write(upn_client_cert_dump)
                print("UPN client cert generated.")

            setup_server_cert(
                redfish_session,
                ca_cert_dump,
                certs_dir,
                client_key,
                client_cert,
                username,
                url,
                server_intermediate_key,
                server_intermediate_cert,
            )

    print("Testing redfish TLS authentication with generated certs.")
    time.sleep(2)
    test_mtls_auth(url, certs_dir)
    print("Redfish TLS authentication success!")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--username",
        help="Username to connect with",
        default="root",
    )
    parser.add_argument(
        "--password",
        help="Password for user in order to install certs over Redfish.",
        default="0penBmc",
    )
    parser.add_argument(
        "--use-intermediate",
        action="store_true",
        default=False,
        help="Generate and use an intermediate certificate",
    )
    parser.add_argument("host", help="Host to connect to")

    args = parser.parse_args()
    generate_and_load_certs(
        args.host, args.username, args.password, args.use_intermediate
    )


if __name__ == "__main__":
    main()

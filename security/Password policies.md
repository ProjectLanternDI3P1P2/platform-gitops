Password Management Policy

Information Systems Security Policy

Table of Contents:

1. Purpose and Scope
2. References and Regulatory Framework
3. Guiding Principles
4. Requirements by Account Type
5. Multi-Factor Authentication (MFA)
6. Secret Management and Storage
7. Formal Prohibitions
8. Procedure in Case of Suspected Compromise
9. Responsibilities

1. Purpose and Scope

This policy defines the rules for creating, using, renewing, and protecting passwords and other authentication secrets within the Lantern Project. It aims to reduce the risk of compromise of user, application, and privileged accounts, which constitutes one of the most frequent intrusion vectors in security incidents.

This policy applies to:

all members within the project;
all systems, applications, network equipment, databases, and services used within the project;
2. References and Regulatory Framework

This policy is based on the following recognized standards, which guarantees its robustness in the face of an audit or certification:

NIST SP 800-63B (Digital Identity Guidelines) — reference US recommendations, favoring length over imposed complexity.
ANSSI — Recommendations regarding multi-factor authentication and passwords.
ISO/IEC 27001 — Annex A, measures A.5.17 (authentication information) and A.8.5 (secure authentication).
CNIL — Recommendations regarding passwords (deliberation No. 2017-012).

Should these standards evolve, this policy will be updated accordingly (see section 12).

3. Guiding Principles

The policy is based on three principles, chosen to balance real security with practicality for users — an overly restrictive password being systematically circumvented (sticky notes, reuse, predictable variants):

Priority given to length rather than artificial complexity: a long password is more robust than a short password stuffed with imposed special characters.
Widespread multi-factor authentication on all sensitive or internet-exposed access.
No password stored or transmitted in plaintext, in any form whatsoever.

4. Requirements by Account Type

The table below summarizes the technical requirements automatically applied by the authentication systems:

Standard user account | 12 characters | 3 of the 4 categories* | No forced expiration (renewal upon suspicion) |
Privileged / admin account | 16 characters | 4 categories mandatory | 90 days |
Service / application account | 20 characters | Randomly generated, managed by vault | Automatic rotation every 90 days or upon each use 

The 4 categories: uppercase letters, lowercase letters, digits, special characters. A passphrase of 16 characters or more without imposed complexity is accepted as an alternative, in accordance with NIST recommendations.

4.1 Recommended Passphrases

Users are encouraged to use passphrases (a combination of words without an obvious logical link) rather than complex, hard-to-remember passwords. Example method: combine 4 to 5 random unrelated words, which produces a secret that is long, memorable, and statistically very robust against brute-force attacks.

5. Multi-Factor Authentication (MFA)

The password alone is no longer considered sufficient protection. MFA is therefore mandatory in the following cases:

any remote access (VPN, remote desktop);
all privileged accounts (system, network, database administrators);
business applications processing sensitive or personal data.

Accepted factors are, in order of preference: physical security key (FIDO2/WebAuthn), authentication application (TOTP), validated push notification.

6. Secret Management and Storage
Passwords are stored exclusively server-side in hashed form using a dedicated algorithm and a unique salt (bcrypt, argon2, or equivalent) — never in plaintext, nor reversibly encrypted without imperative necessity.
The use of an enterprise password manager is mandatory for all privileged accounts and strongly recommended for all employees.
Service account passwords are stored in a digital vault with automated rotation and access traceability.
No password should be sent by email, instant messaging, or written into an unencrypted shared file.

7. Formal Prohibitions

The following are strictly prohibited, and detected as much as possible through automated technical controls:

reuse of the same password across multiple accounts, professional or personal;
the use of passwords appearing in known public data breach lists (verification via an API such as "Have I Been Pwned" or an internal equivalent);
trivial or predictable passwords (name, season + year, keyboard sequences, personal information);
sharing a personal password among several people, including within the same team;
saving a password in plaintext in a browser not protected by a master password, on a sticky note, or in an unencrypted office file;
retaining the default passwords of equipment and applications beyond the installation phase.

8. Procedure in Case of Suspected Compromise

In case of doubt about the compromise of a password (phishing, loss of equipment, security alert, abnormal account behavior), the user must:

Immediately change the password in question;
report the incident without delay to the Security team or via the dedicated reporting channel (Teams Channel);
not wait for confirmation before acting: the precautionary principle prevails.

The security team then conducts an analysis (connection logs, suspicious activity) and may trigger revocation of active sessions, forced rotation on linked accounts, or a broader incident management procedure depending on criticality.

9. Responsibilities
Security Team: defines, maintains, and evolves this policy; technically implements the requirements (password policies, MFA, vaults) and ensures their proper functioning.
Others members of the project: apply the defined rules, report any incident, and complete the training offered.
# The PEP Opacity Layer

STRUCTURE: Offshore entities controlled by or connected to politically exposed persons (PEPs) through nominee structures designed to obscure the PEP's involvement. The PEP's name does not appear in the entity's public records; instead, nominees, family members, or close associates serve as directors and shareholders.
JURISDICTIONS: Entities in high-secrecy jurisdictions; PEP typically based in a jurisdiction with anti-corruption scrutiny (OECD, EU), making opacity a necessity rather than a convenience
INDICATORS: An ICIJ entity whose officers or connected persons match PEP entries in OpenSanctions (topic: role.pep), with nominee directors interposed. The PEP's own name may not appear at all — look for family members, known associates, or professional nominees who serve on other PEP-connected entities.
RISK LEVEL: HIGH
STATUS: PROPOSED
OBSERVED IN: To be confirmed through cross-referencing ICIJ and OpenSanctions data

## Mechanism

Politically exposed persons — heads of state, senior government officials, judges, military officers, and their family members and close associates — face enhanced due diligence requirements at financial institutions worldwide. A PEP who wishes to hold offshore assets without triggering these requirements may structure their holdings through opacity layers:

1. The PEP does not appear as a director, shareholder, or beneficial owner of the offshore entity
2. Nominees — professional directors, trusted associates, or family members not themselves classified as PEPs — hold the formal positions
3. The PEP's control is exercised through power of attorney, side agreements, or informal arrangements not reflected in corporate records
4. The intermediary (law firm, trust company) managing the structure may or may not be aware of the PEP's involvement

The structure achieves two things: it allows the PEP to hold assets outside the jurisdiction where they exercise political power, and it prevents the enhanced due diligence that would apply if their name appeared in the entity's records.

## Detection

Using the MCP tools:
1. `/investigate` a known PEP — check both ICIJ and OpenSanctions
2. If the PEP does not appear directly in ICIJ, search for known family members and associates (from OpenSanctions PEP data, which includes relatives and close associates)
3. Use `sanctions_entity` (nested=true) on the PEP's OpenSanctions entry to get connected persons — then search ICIJ for those names
4. If family members or associates appear as ICIJ officers, examine whether nominee structures (The Nominee Shield pattern) are interposed
5. The combination of PEP status (OpenSanctions) + family/associate as officer (ICIJ) + nominee directors (ICIJ) is the signature of this pattern

## Examples

To be populated through cross-reference investigations.

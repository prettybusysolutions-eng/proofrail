# Deviations From Supplied ESRM Language

- Repair 1 is rejected as canonical baseline because it replaced supplied protocol numbering and semantics.
- Repair 2 restores the supplied Section 22 title, supplied transition package shape, supplied signature envelope shape, uppercase domains, and domain-separated commitment construction based on the audit text.
- Full verbatim supplied Sections 22-40 were not present as an independent source file in the repository. Any supplied sentence not represented in `ESRM_PROTOCOL_SECTIONS_22_40.md` remains `AMB-006` and blocks implementation until independent audit confirms preservation.
- Harness requirements are separated into `ESRM_CONFORMANCE_HARNESS_REQUIREMENTS.md` and do not reuse ESRM protocol section numbers.

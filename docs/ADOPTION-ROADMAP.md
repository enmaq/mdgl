# MDGL adoption roadmap

Status: informative plan, not a decision. Reviewed for factual consistency (independent review and a maintainer review pass); remains an unadopted project proposal; not an IETF, RFC Editor or IANA document or endorsement; SPEC.md remains authoritative; no normative adoption is implied by the reviews. The circle clarification is a SPEC.md change made by the project maintainers, not by the review. Status note: the circle size bound was resolved by a project maintainers' decision (SPEC.md clarification: radius <= 100, diameter <= 200); confirmation is pending, because the TypeScript adapter is being corrected and the cross-language boundary fixtures are being added (RFC 0001 section 4.4). It describes an order of work. It takes no IETF, IANA or
registry action and claims no standards-body status. See
[RFC 0001](../rfcs/0001-mdgl-interoperability-and-registration-roadmap.md) for the evidence and open questions.

1. **Specification and tests first.** Decide the open questions in RFC 0001 section 10 one at a time (raster
   extents and offset first), land each accepted answer in `SPEC.md` with fixtures, and promote reference-profile
   fixtures to normative only where SPEC then says so. Keep the 86-fixture corpus (46 legacy + 40 observable; full-corpus independent verification pending) and the runner green for all five
   adapters.
2. **Release the validated implementations.** Bump `VERSION`, publish the currently unreleased Rust, C,
   TypeScript/JS and Python cores, and update the language table in [README.md](../README.md).
3. **Invite second implementers.** Point outside implementers to the [adopter guide](ADOPTER-GUIDE.md); ask them to
   run the runner and report gaps as RFCs or issues.
4. **Optional, later: a media-type application.** Only if a stable spec and independent implementations exist and
   the author wants it: consider `text/vnd.enmaq.mdgl` through the IANA form. It is unregistered, subject to review,
   with the author/ENMAQ as change controller; no exclusive-ownership, trademark or approval claim is made.

# Publishing MDGL as an Internet-Draft

This is a practical guide to proposing MDGL to the IETF document community. It does not mean MDGL has been submitted to the IETF, adopted by a working group, or approved for publication as an RFC.

## Where MDGL stands

MDGL's current project definition is [`../SPEC.md`](../SPEC.md), with examples and expected results in [`../conformance/`](../conformance/). The project also has an [RFC-style interoperability and registration roadmap](../rfcs/0001-mdgl-interoperability-and-registration-roadmap.md), an [adopter guide](ADOPTER-GUIDE.md), and an [adoption roadmap](ADOPTION-ROADMAP.md). These are project-maintained drafts, not IETF Internet-Drafts or RFCs. The project RFC-style draft states that it was reviewed for factual consistency (independent review and a maintainer review pass) but remains an unadopted project proposal, that no normative adoption is implied by the reviews, and that it adds no normative decisions; `SPEC.md` remains the normative project text. The current specification describes itself as a **reference subset**; it reserves some features and says the syntax may change. Before asking outsiders to implement against a stable contract, publish a complete, versioned specification and keep the conformance cases aligned with it.

[RFC 7763](https://www.rfc-editor.org/rfc/rfc7763.html) is an Informational RFC that registers the `text/markdown` media type; it does not define Markdown syntax. It is a useful example of a registration RFC, not a template that makes MDGL an IETF language. An Internet-Draft can invite review, but it has no formal status and can change or expire. Posting one does not make it an IETF standard or guarantee an RFC.

## Choose the route

For a first public proposal, the simplest route is an **individual Internet-Draft**: the project maintainer writes and submits it, then invites review. Anyone can author an I-D. If an existing IETF working group later agrees that the topic belongs in its charter and adopts the work, the draft becomes a working-group document under that group's process. Do not use a `draft-ietf-<group>-…` name or claim WG consensus before the group has adopted it.

Posting an individual I-D is not the same as submitting it into an RFC publication stream. For the IETF stream, an individual RFC submission normally needs an Area Director to agree to sponsor it and take it through IETF/IESG review; a working-group document follows the group's consensus and shepherding process. The Independent Submissions Editor (ISE) is a separate RFC stream for appropriate work outside the IETF, IAB, and IRTF processes. IAB and IRTF streams have their own scope and approvers; the Editorial stream handles RFC Series policy. Each route has separate review and approval. See the current [IESG sponsorship guidance](https://datatracker.ietf.org/doc/statement-iesg-guidance-on-area-director-sponsoring-of-documents-20070320/) before pursuing an individual IETF-stream RFC. RFCs are not all standards: their status can be Standards Track, Informational, Experimental, or another defined status. An RFC number is assigned only if a stream approves the document and it reaches RFC publication.

## Prepare the first draft

1. **Decide what readers should review.** Use a complete version of the language definition, examples, error behavior, security considerations, and conformance material. Clearly list what is implemented, what is reserved, and what remains unsettled. State whether the draft represents only its authors or has been adopted by a group. For current MDGL content, start from [`../SPEC.md`](../SPEC.md) and [`../conformance/`](../conformance/), and label their present project status accurately.
2. **Choose the intended stream and status honestly.** For an individual proposal, suggest an author-name-based identifier. A possible first identifier is `draft-brunko-mdgl-language-00`; use the same identifier in the source metadata and verify it on the Datatracker validation screen. The `-00` is the initial revision. Later revisions increment the suffix (`-01`, `-02`, …). The `draft-ietf-<wg>-…` form is for work adopted by that working group, not merely work related to it. See the current [Internet-Draft Author Resources](https://authors.ietf.org/) and submission screen for current instructions.
3. **Fill in the document metadata from an official template.** Include a concise title, an abstract that accurately describes the document, author names and affiliations as appropriate, the intended status/category, and the fields required by the selected RFCXML template. Make sure every listed author has reviewed the text and is comfortable being listed. The I-D author list is separate from the IANA media-type `Change Controller` field described below. Author contact details in the draft and Datatracker are public, so decide deliberately which address to publish; an IETF account email is not automatically the right public contact. The account used to submit need not be named in this repository or in the draft.
4. **Choose one authoring format.** The Datatracker currently prefers a standalone **xml2rfc v3 XML** source. Markdown is also supported through toolchains such as `kramdown-rfc`, but Markdown dialects and toolchains differ; choose one and follow its own template and instructions. If XML is new to you, begin with the [RFCXML authoring guide](https://authors.ietf.org/drafting-in-xml) and its template. The [Markdown authoring guide](https://authors.ietf.org/drafting-in-markdown) explains the trade-offs. The [IETF Author Tools web-service guide](https://authors.ietf.org/author-tools-web-service) explains how to validate and render supported sources without a local tool installation.

### Render and check an XML draft locally

Install a current xml2rfc v3 release using the [xml2rfc package instructions](https://pypi.org/project/xml2rfc/) or use the [IETF Author Tools web service](https://authors.ietf.org/author-tools-web-service). From the directory containing the source, render both text and HTML:

```sh
xml2rfc --version
xml2rfc --text draft-brunko-mdgl-language-00.xml
xml2rfc --html draft-brunko-mdgl-language-00.xml
```

The default renderer is v3; `--text` and `--html` write output files next to the source unless an output path is supplied. Treat warnings as review items; verify the rendered text, references, author metadata, page headers, and boilerplate before upload. If the XML source is named differently, replace the example filename consistently. Do not use a successful render as a substitute for the Datatracker validation screen.

Run current [idnits](https://github.com/ietf-tools/idnits) against the rendered text if it is installed:

```sh
idnits draft-brunko-mdgl-language-00.txt
```

The current idnits tool also accepts a URL. Alternatively, use the idnits link on the [Datatracker submission page](https://datatracker.ietf.org/submit/). The submission page recommends idnits; it does not replace technical review.

## Submit and publish a revision

1. Read the current [Internet-Draft submission instructions](https://datatracker.ietf.org/submit/tool-instructions/) and [Note Well](https://www.ietf.org/about/note-well/), including [BCP 78 / RFC 5378](https://www.rfc-editor.org/rfc/rfc5378.html), before uploading. Submission grants rights to the IETF Trust. Understand the contribution and intellectual-property rules, and disclose relevant patent claims under the IETF IPR policy when applicable. The IETF keeps public records, including contributor information.
2. Open the [Datatracker submission form](https://datatracker.ietf.org/submit/), upload the standalone v3 XML, and inspect the parsed title, authors, document name, intended status, and every validation result. XML lets Datatracker generate the presentation formats. If XML cannot be submitted, the current tool accepts a plaintext rendering instead. Resolve validation errors and correct bad metadata before proceeding.
3. Authenticate with the IETF Datatracker account or follow the confirmation email workflow shown by the tool. The current instructions say confirmation for a new `-00` goes to the listed authors; a replacement revision goes to authors of the previous version. Working-group `-00` submissions may require chair approval. Follow the current screen for the exact confirmation required. Do not assume that an upload alone has posted the draft.
4. After posting, use the resulting Datatracker document page as the canonical public link. For each substantive update, edit the same source, regenerate and review its renderings, address comments, then submit a new revision through the same tool. Keep the document identifier and increment the revision. Internet-Drafts currently expire after at most six months; check the Datatracker page and renew with a new revision when appropriate. A later version can be updated, replaced, or withdrawn; the old revision is not silently rewritten.
5. Share the Datatracker link with relevant reviewers and, if there is a plausible IETF working-group fit, ask the chairs or mailing list how to discuss adoption. Adoption is a group decision under its charter and process; it is not obtained by choosing a filename. Keep the distinction between individual author intent and WG consensus explicit in every revision.

The submission form displays any current meeting cut-off dates. Those dates change, so check the form at the time you submit rather than copying a date into project documentation.

## Optional: register a media type later

RFC 7763 is about a media type, while the [MDGL specification](../SPEC.md) must define the language itself. A media type is optional and should follow a stable, publicly reviewable format definition. RFC 6838, as updated by [RFC 9694](https://www.rfc-editor.org/rfc/rfc9694.html), explains the registration trees and top-level types; check the IANA form and current media-type procedure again when a registration is actually prepared.

The unregistered candidate `text/vnd.enmaq.mdgl` is only a discussion placeholder; even whether `enmaq` is the right vendor facet needs review. RFC 6838's `text` type is for content principally textual in form and has charset requirements; `application` covers discrete data intended for processing by software, including active/computational languages. Because MDGL is readable source that is also interpreted by renderers, decide the top-level type with media-type experts based on its real interchange and processing model. Do not advertise either candidate as registered or approved.

For a vendor registration, RFC 6838 permits the producer to request a `vnd.` subtype through IANA's [media-type registration form](https://www.iana.org/form/media-types); expert review is required. Public review on the IETF media-types list is encouraged. Prepare the required specification URL, security considerations, encoding/charset behavior, interoperability notes, intended usage, author/contact, and a clear change controller. The change controller is the person or organization responsible for future updates to the registration; agree on that responsibility before submitting. A standards-tree type is a different route with a formal standards specification and its applicable approval process. Registration identifies a media type; it does not certify MDGL or turn its project specification into an RFC.

## References and current project links

- [MDGL project specification](../SPEC.md)
- [MDGL conformance cases](../conformance/)
- [MDGL project RFC-style draft](../rfcs/0001-mdgl-interoperability-and-registration-roadmap.md) (not an IETF RFC or Internet-Draft)
- [MDGL adopter guide](ADOPTER-GUIDE.md) and [adoption roadmap](ADOPTION-ROADMAP.md)
- [RFC 7763: The `text/markdown` Media Type](https://www.rfc-editor.org/rfc/rfc7763.html)
- [IETF Internet-Drafts: status and submission overview](https://www.ietf.org/how/ids/)
- [IETF RFC streams](https://www.ietf.org/process/rfcs/)
- [RFC 6838: Media Type Specifications and Registration Procedures](https://www.rfc-editor.org/rfc/rfc6838.html)
- [RFC 9694: Guidelines for the Definition of New Top-Level Media Types](https://www.rfc-editor.org/rfc/rfc9694.html)

# Experimental camera privacy notice

This notice applies only to the camera-enabled experimental candidate. The
separately published v1.0.2 benchmark remains described by its historical notice.

## Camera and processing

Camera permission is requested only after you choose Open camera. Audio is not
requested. Capture one food item before and after in comparable conditions;
keep people, documents and personal details out of frame. The browser processes
the selected frames on your device. It does not send photos, starting mass or
estimates to an inference API. There are no accounts, analytics, cookies,
application databases or automatic photo history.

The camera stops when the page is hidden, on navigation/reset and on component
cleanup. Hiding the page clears estimates but does not discard the in-memory
pair. Clear, reload or leaving the page releases the current pair. Browser/OS
copies and immutable memory cannot be guaranteed forensically erased.

The model and runtime are downloaded as static files from the same site only
when you explicitly request an estimate. The model's SHA-256 is checked before
inference. Downloads of site assets are network requests; a hosting provider
such as GitHub Pages and your network may process ordinary visitor/request
metadata. "On-device" does not mean that visiting a website makes no requests.

## Explicit session files

Save session downloads an **unencrypted** `.plategauge.json` file that contains
the photos, exact model crops, optional starting mass and compatibility fields.
No file is saved automatically. Resume session reads a file you explicitly
select, validates it, and asks before replacing an existing pair. Saved results
are not restored; estimating requires another explicit action.

Keep session files private. Downloads, synced folders, backups and file sharing
are controlled by your browser/OS, not PlateGauge. Clear does not delete a file
you downloaded. Delete it yourself when no longer needed. Resume only files you
trust. The corruption checksum is not a signature or proof of capture identity;
imported JPEG metadata is not promised to be stripped.

## Optional device check

An optional, collapsed device check lets you record choices and workflow
outcomes and explicitly download a small report. It contains no photos, masses,
estimates, names, device identifiers or free-text notes. It is not sent anywhere
by the app. Timing observations and self-reported device outcomes are not model
accuracy evidence or a certification of phone compatibility.

## Purpose and limitations

The estimate is an experimental output from the existing research baseline,
not a measured weight, calibrated confidence interval, meal-intake assessment,
scale replacement or operational recommendation. The model does not learn from
your photos. Do not use it for medical, nutritional, purchasing or safety
decisions. See [the camera system card](CAMERA_SYSTEM_CARD.md).

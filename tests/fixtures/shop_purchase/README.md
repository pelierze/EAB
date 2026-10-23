# Purchased friendship-point row

`friendship_sold_20261023.npz` contains uint8 BGR arrays from the local
2026-10-23 16:30:57 failure report and its debug evidence:

- `row`: the post-purchase screenshot cropped to `[x=536, y=76, w=715, h=130]`.
  The friendship-point slot is `[24, 24, 82, 82]` within this crop and its
  purchased button is `[526, 62, 183, 53]`.
- `before_button`: the actual pre-purchase button saved by that run's debug
  recorder. It shows `1/1`; the post-purchase row shows `0/1`.

The actual pre-purchase item screenshot was not retained. Tests use the existing
`images/items/friendship_point.png` asset as its representative item reference;
they do not claim to replay a complete pair of live before/after captures.
The crop excludes the account's top-bar currency totals and other unrelated UI.
These are test data, excluded from release asset collection.

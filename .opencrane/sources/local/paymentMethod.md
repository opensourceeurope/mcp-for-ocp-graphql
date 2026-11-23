# `paymentMethod` query

Returns `PaymentMethod`.

Get a payment method by reference. Returns null if it does not exist or if the logged in user is not an admin of the account that owns it. Scope: "orders".

Arguments: `paymentMethod` (PaymentMethodReferenceInput!, required).

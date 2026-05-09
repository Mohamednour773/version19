# -*- coding: utf-8 -*-
# This file is intentionally minimal.
#
# The club_membership_summary non-stored computed field that was previously
# defined here has been removed in v19.0.1.0.2.
#
# Reason: non-stored computed fields on pos.order.line are never transmitted
# to the POS frontend for receipt rendering — the receipt operates on local
# client-side order objects. Membership details on the custom receipt are now
# fetched via a direct ORM RPC call (club.membership.get_pos_receipt_memberships)
# from the OrderReceipt component's setup() hook.

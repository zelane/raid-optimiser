"""
forms - the boundary between what pages post and the model: each form's fields into typed
values, or the reasons they can't be (`FormErrors`); past here nothing sees raw fields. The
champion page's request form and its build buttons are `request`; the forms that change what's
stored (locks, assumptions, reserve rules, the accessories pages' weights, spaces, protection
and selling), `settings`; the Chimera page's query, `chimera`; what they share, `common`.
"""

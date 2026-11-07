from django.shortcuts import redirect


class MustChangePasswordMiddleware:
    """Keep temporary-password accounts on the password-change page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated or not request.user.must_change_password:
            return None
        if request.resolver_match.url_name in ("password_change", "logout"):
            return None
        return redirect("password_change")

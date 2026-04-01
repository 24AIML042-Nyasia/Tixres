from django.shortcuts import render


def feature_client_ui(request):
    """
    Serve the legacy metrics + tickets UI with the current host as the default base URL.
    """
    default_base = request.build_absolute_uri("/").rstrip("/")
    return render(request, "guidance/feature_client.html", {"default_base_url": default_base})


def guidance_ui(request):
    """
    Serve the guidance library UI sharing the same design language.
    """
    default_base = request.build_absolute_uri("/").rstrip("/")
    return render(request, "guidance/guidance_client.html", {"default_base_url": default_base})


def auth_ui(request):
    """
    Auth UI (login/register/admin) for demo/dev environments.
    """
    default_base = request.build_absolute_uri("/").rstrip("/")
    return render(request, "guidance/auth_client.html", {"default_base_url": default_base})


def guidance_doc(request):
    """
    Render guidance document detail page (client fetches by query params).
    """
    default_base = request.build_absolute_uri("/").rstrip("/")
    return render(request, "guidance/guidance_doc.html", {"default_base_url": default_base})

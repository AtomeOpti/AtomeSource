import requests

# À remplacer par l'URL HTTPS de ton serveur.
LICENSE_SERVER_URL = ""


def activate_premium(key: str) -> tuple[bool, str]:
    key = key.strip()

    if not key:
        return False, "Veuillez entrer une clé."

    try:
        response = requests.post(
            f"{LICENSE_SERVER_URL}/activate",
            json={
                "key": key,
                "product": "premium"
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return False, "Serveur de licences inaccessible."

    if data.get("ok"):
        return True, "Premium activé."

    reasons = {
        "invalid": "Clé invalide.",
        "already_used": "Cette clé a déjà été utilisée.",
        "expired": "Cette clé a expiré.",
    }
    return False, reasons.get(
        data.get("reason"),
        "Clé refusée."
    )


# Exemple :
#
# ok, message = activate_premium("PPC-XXXXX-XXXXX-XXXXX-XXXXX")
# if ok:
#     # afficher / ouvrir l'optimisation Premium
# else:
#     # afficher message d'erreur

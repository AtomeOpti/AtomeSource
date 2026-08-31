import requests


LICENSE_SERVER_URL = "??"


def activate_free(key):

    key = key.strip()

    if not key:
        return False, "Clé vide."


    try:

        response = requests.post(
            f"{LICENSE_SERVER_URL}/activate",
            json={
                "key": key,
                "product": "free"
            },
            timeout=10
        )

        response.raise_for_status()

        data = response.json()


    except Exception as exc:

        return False, f"Erreur serveur : {exc}"


    if data.get("ok"):

        return True, "Optimisation gratuite activée."


    reason = data.get("reason", "")


    if reason == "expired":
        return False, "Clé expirée."

    if reason == "already_used":
        return False, "Clé déjà utilisée."

    return False, "Clé invalide."
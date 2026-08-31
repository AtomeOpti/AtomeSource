<img width="1919" height="1028" alt="Capture d&#39;écran 2026-08-31 031239" src="https://github.com/user-attachments/assets/7f70afb5-95d3-4b2c-940a-4edca815755f" />
# AtomeOpti

AtomeOpti est une application Windows d'optimisation système (nettoyage,
réglages Windows, gestion du démarrage, désinstallation, monitoring
matériel...) avec des fonctions Premium débloquables par clé d'activation.

Ce dépôt contient le **code source de référence** du client de bureau, publié
à titre de transparence.

## ⚠️ Important — installe depuis le site, pas depuis ce dépôt

- **Ce code source n'est pas maintenu en continu.** La version qui compte, à
  jour et supportée, est celle publiée sur le site officiel.
- **Ce dépôt ne peut pas être compilé ni exécuté tel quel.** Le programme
  dépend volontairement d'un module de build privé qui n'est pas distribué
  publiquement (voir la section [Pourquoi ça ne compile pas](#pourquoi-ça-ne-compile-pas)).
- Pour utiliser AtomeOpti, télécharge l'exécutable officiel ici :

  **👉 Télécharger AtomeOpti : [https://atomeopti.github.io/]

 

## Contenu du dépôt

| Fichier / dossier      | Rôle |
|-------------------------|------|
| `main.py`               | Interface et logique de l'application (customtkinter). |
| `premium_client.py`     | Appel HTTP au serveur de licences pour l'activation Premium. |
| `free_client.py`        | Appel HTTP au serveur de licences pour l'activation Free. |
| `assets/`                | Icônes et visuels de l'interface. |
| `requirements.txt`      | Dépendances Python. |
| `build_exe.bat`          | Script d'exemple de packaging PyInstaller (usage interne). |
| `NOTICE.md`              | Origine des ressources graphiques tierces utilisées dans l'UI. |
| `LICENSE.md`             | Conditions d'utilisation de ce dépôt. |

## Pourquoi ça ne compile pas

L'activation Premium/Free d'AtomeOpti est vérifiée **exclusivement côté
serveur** (aucune clé n'est générée ni validée localement). Pour éviter que
ce dépôt public serve de base à une version modifiée qui contournerait cette
vérification, `main.py` importe un petit module privé
(`atomeopti_build`) qui n'existe que sur l'environnement de build officiel.
Sans lui, le programme s'arrête au démarrage avec un message explicite.

C'est volontaire : ce dépôt sert à **lire** le code, pas à produire un
exécutable fonctionnel.

## Lire / contribuer

```bash
pip install -r requirements.txt
python main.py   # s'arrête volontairement (voir ci-dessus)
```

Les retours, rapports de bugs et suggestions sont les bienvenus via les
issues GitHub.

## Licence

Voir [LICENSE.md](LICENSE.md) — dépôt "source-available", pas open-source :
lecture et contribution proposée autorisées, compilation/redistribution non
autorisées sans accord écrit.

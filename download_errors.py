"""Classification des erreurs de telechargement / de sonde (yt-dlp, gallery-dl).

Module feuille : bibliotheque standard uniquement.

classify_error(error) -> (kind, reason)
    kind   : 'permanent' (video supprimee, privee, introuvable, restreinte par pays, compte
             supprime...) ou 'transient' (403, 429, 5xx, delais, reseau, captcha, JSON
             illisible... et tout ce qui est ambigu : par defaut une erreur est temporaire,
             l'element est alors retente au plus link_state.MAX_ATTEMPTS fois).
    reason : courte phrase en francais.
"""
import re

# Statuts TikTok renvoyes par yt-dlp ("Video not available, status code N") qui signifient
# une indisponibilite definitive : 10204 = element inexistant / supprime, 10216 = video
# privee, 10222 = compte prive. Les autres codes restent ambigus (temporaires).
_PERMANENT_TIKTOK_STATUS = {"10204", "10216", "10222"}

# (motif, raison) testes dans l'ordre ; le premier qui correspond l'emporte.
_PERMANENT = [
    (r"\bthis (?:video|post) is private\b|\bprivate (?:video|post)\b|"
     r"\bvideo is private\b|\baccount is private\b|\bthis account is private\b",
     "Vidéo privée"),
    (r"available in your (?:country|region)|geo[- ]?restrict|"
     r"blocked in your (?:country|region)|not available in this (?:country|region)",
     "Vidéo non disponible dans ce pays"),
    (r"\baccount (?:has been |was )?(?:banned|suspended|deleted|removed)\b|"
     r"\buser (?:does not|doesn't) exist\b|couldn'?t find this account|"
     r"\baccount (?:does not|doesn't) exist\b",
     "Compte supprimé ou introuvable"),
    (r"\b(?:has|have) been (?:removed|deleted)\b|\bwas (?:removed|deleted)\b|"
     r"\bremoved by the (?:user|author|uploader|creator)\b|"
     r"\bvideo (?:has been )?taken down\b|violat(?:ed|ing|ion of) (?:our )?community guidelines",
     "Vidéo supprimée"),
    (r"\b(?:video|post|item) (?:does not|doesn't|no longer) exists?\b|"
     r"\bcould not be found\b|couldn'?t find this (?:video|post)|"
     r"\bpost not (?:found|available)\b|\bvideo not found\b",
     "Vidéo introuvable"),
    (r"\bvideo (?:is )?unavailable\b|\bthis (?:video|post) is (?:currently )?unavailable\b|"
     r"\bvideo (?:is )?no longer available\b|\bunavailable video\b",
     "Vidéo indisponible"),
    (r"\bhttp ?error 404\b|\b404[: ]+not found\b|'404 not found'|\bstatus(?: code)?[: ]+404\b",
     "Vidéo introuvable (HTTP 404)"),
    (r"\bhttp ?error 410\b|\b410[: ]+gone\b|'410 gone'|\bstatus(?: code)?[: ]+410\b",
     "Vidéo supprimée (HTTP 410)"),
]

_TRANSIENT = [
    (r"\bhttp ?error 403\b|\b403[: ]+forbidden\b|'403 forbidden'|\bforbidden\b",
     "Accès refusé (HTTP 403) : cookies expirés ou blocage temporaire"),
    (r"\bhttp ?error 429\b|\b429\b|too many requests|rate[- ]?limit",
     "Trop de requêtes (HTTP 429) : limitation de TikTok"),
    (r"\bhttp ?error 5\d\d\b|\b5\d\d[: ]+(?:internal server error|bad gateway|"
     r"service unavailable|gateway time-?out)\b|'5\d\d [a-z ]+'",
     "Erreur du serveur TikTok (HTTP 5xx)"),
    (r"captcha|verify (?:you are|that you're) (?:a )?human|\bverification required\b",
     "Vérification anti-robot (captcha) demandée"),
    (r"ip address is blocked|\bip (?:has been )?blocked\b",
     "Adresse IP bloquée temporairement"),
    (r"timed? ?out|\btimeout\b|délai",
     "Délai d'attente dépassé"),
    (r"getaddrinfo|name or service not known|temporary failure in name resolution|"
     r"nodename nor servname|no address associated|\bdns\b",
     "Erreur réseau (résolution DNS)"),
    (r"connection (?:reset|refused|aborted|error)|remote end closed|reset by peer|"
     r"\bconnectionerror\b|\burlerror\b|network is unreachable|\bssl\b|"
     r"incompleteread|broken pipe|forcibly closed|unable to download webpage",
     "Erreur réseau"),
    (r"failed to parse json|jsondecodeerror|expecting value",
     "Réponse illisible de TikTok (JSON invalide)"),
    (r"unable to extract (?:webpage )?video data|unable to extract universal data|"
     r"unable to extract sigi state|unable to extract",
     "Données de la vidéo introuvables dans la page"),
    (r"gallery-dl n'est pas installé|gallery-dl is not installed",
     "gallery-dl n'est pas installé"),
]

_STATUS_RE = re.compile(r"video not available,? status code (\d+)", re.IGNORECASE)
_PERMANENT_RE = [(re.compile(p, re.IGNORECASE), r) for p, r in _PERMANENT]
_TRANSIENT_RE = [(re.compile(p, re.IGNORECASE), r) for p, r in _TRANSIENT]

DEFAULT_REASON = "Erreur temporaire ou inconnue"


def _message(error):
    if error is None:
        return ""
    if isinstance(error, BaseException):
        text = str(error)
        name = type(error).__name__
        return f"{name}: {text}" if text else name
    return str(error)


def classify_error(error):
    """Classe une erreur (exception ou message). Retourne (kind, reason)."""
    if isinstance(error, TimeoutError):
        return "transient", "Délai d'attente dépassé"
    text = _message(error)
    if not text.strip():
        return "transient", DEFAULT_REASON
    status = _STATUS_RE.search(text)
    if status:
        if status.group(1) in _PERMANENT_TIKTOK_STATUS:
            reason = ("Vidéo privée" if status.group(1) in ("10216", "10222")
                      else "Vidéo supprimée ou inexistante")
            return "permanent", reason
        return "transient", f"Vidéo momentanément indisponible (code TikTok {status.group(1)})"
    for regex, reason in _PERMANENT_RE:
        if regex.search(text):
            return "permanent", reason
    for regex, reason in _TRANSIENT_RE:
        if regex.search(text):
            return "transient", reason
    if isinstance(error, (ConnectionError, OSError)):
        return "transient", "Erreur réseau"
    return "transient", DEFAULT_REASON

// Export des liens de vidéos d'un profil TikTok (à coller dans la console du navigateur).
// À lancer sur la page d'un profil (https://www.tiktok.com/@pseudo), dans votre navigateur connecté.
// Aucune dépendance, aucun appel d'API : lit seulement les liens déjà présents dans la page.
// Réglages facultatifs : définir window.EXPORT_LIENS_OPTIONS = {stepMs, idleMs, maxMs} avant.
(async () => {
  const o = Object.assign({ stepMs: 1000, idleMs: 6000, maxMs: 900000 }, window.EXPORT_LIENS_OPTIONS);
  const profil = location.pathname.match(/^\/@([\w.\-]+)/);
  if (!profil) return console.error('Ouvrez d\'abord la page d\'un profil : https://www.tiktok.com/@pseudo');
  const pseudo = profil[1], cle = pseudo.toLowerCase();
  const liens = new Map(); // id -> URL propre (sans paramètres), doublons écartés

  // Relève les ancres /video/ et /photo/ qui appartiennent bien à CE profil (pas aux suggestions)
  const collecter = () => document.querySelectorAll('a[href*="/video/"], a[href*="/photo/"]').forEach(a => {
    let chemin;
    try { chemin = new URL(a.getAttribute('href'), location.href).pathname; } catch (e) { return; }
    const m = chemin.match(/^\/@([\w.\-]+)\/(video|photo)\/(\d+)/);
    if (m && m[1].toLowerCase() === cle && !liens.has(m[3]))
      liens.set(m[3], `https://www.tiktok.com/@${m[1]}/${m[2]}/${m[3]}`);
  });

  // Défile vers le bas jusqu'à ce qu'aucun nouveau lien n'apparaisse pendant idleMs (ou maxMs au total)
  const debut = Date.now();
  let dernierGain = debut, nb = -1;
  while (Date.now() - debut < o.maxMs && Date.now() - dernierGain < o.idleMs) {
    collecter();
    if (liens.size !== nb) { nb = liens.size; dernierGain = Date.now(); console.log(`${nb} liens trouvés pour @${pseudo}...`); }
    window.scrollTo(0, document.documentElement.scrollHeight);
    window.scrollBy(0, -50); // petit retour : relance le chargement paresseux
    await new Promise(r => setTimeout(r, o.stepMs));
    window.scrollTo(0, document.documentElement.scrollHeight);
  }
  collecter();

  // Fichier texte : une URL par ligne
  const texte = [...liens.values()].join('\n') + '\n';
  const lien = document.createElement('a');
  lien.href = URL.createObjectURL(new Blob([texte], { type: 'text/plain;charset=utf-8' }));
  lien.download = `tiktok_liens_${pseudo}.txt`;
  document.body.appendChild(lien); lien.click(); lien.remove();
  try { await navigator.clipboard.writeText(texte); console.log('Liste copiée dans le presse-papiers.'); }
  catch (e) { console.log('Copie automatique impossible : utilisez le fichier téléchargé.'); }
  console.log(`Terminé : ${liens.size} liens pour @${pseudo} (fichier tiktok_liens_${pseudo}.txt).`);
  window.__exportLiens = { pseudo, total: liens.size };
})();

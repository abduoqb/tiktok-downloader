"""
Module d'export des données
Exporte les métadonnées en différents formats (CSV, JSON, HTML)
"""
import csv
import json
import os
from datetime import datetime
from main import get_metadata_manager, get_user_dir


class DataExporter:
    """Gestionnaire d'exports de données"""

    def __init__(self, username):
        """
        Initialize exporter

        Args:
            username: Nom d'utilisateur à exporter
        """
        self.username = username
        self.manager = get_metadata_manager(username)
        self.user_dir = get_user_dir(username)

    def export_to_csv(self, output_file=None):
        """
        Exporte les métadonnées en CSV

        Args:
            output_file: Chemin du fichier de sortie (optionnel)

        Returns:
            str: Chemin du fichier généré
        """
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = os.path.join(self.user_dir, f"{self.username}_export_{timestamp}.csv")

        self.manager.load()
        metadata = self.manager._metadata

        # Écrire le CSV
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['id', 'url', 'type', 'date', 'size_bytes', 'size_mb',
                         'file_count', 'success', 'tags', 'favorite', 'notes']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()

            for video_id, data in metadata.items():
                size_bytes = data.get('size', 0)
                size_mb = round(size_bytes / (1024 * 1024), 2) if size_bytes else 0

                writer.writerow({
                    'id': video_id,
                    'url': data.get('url', ''),
                    'type': data.get('type', ''),
                    'date': data.get('date', ''),
                    'size_bytes': size_bytes,
                    'size_mb': size_mb,
                    'file_count': data.get('file_count', 1),
                    'success': data.get('success', True),
                    'tags': ','.join(data.get('tags', [])),
                    'favorite': data.get('favorite', False),
                    'notes': data.get('notes', '')
                })

        print(f"Export CSV créé: {output_file}")
        return output_file

    def export_to_json(self, output_file=None, pretty=True):
        """
        Exporte les métadonnées en JSON

        Args:
            output_file: Chemin du fichier de sortie (optionnel)
            pretty: Si True, formate le JSON (défaut: True)

        Returns:
            str: Chemin du fichier généré
        """
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = os.path.join(self.user_dir, f"{self.username}_export_{timestamp}.json")

        self.manager.load()
        metadata = self.manager._metadata

        # Enrichir avec stats
        export_data = {
            'username': self.username,
            'export_date': datetime.now().isoformat(),
            'total_items': len(metadata),
            'statistics': self._get_stats(),
            'videos': metadata
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            if pretty:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            else:
                json.dump(export_data, f, ensure_ascii=False)

        print(f"Export JSON créé: {output_file}")
        return output_file

    def export_to_html(self, output_file=None):
        """
        Exporte les métadonnées en HTML

        Args:
            output_file: Chemin du fichier de sortie (optionnel)

        Returns:
            str: Chemin du fichier généré
        """
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = os.path.join(self.user_dir, f"{self.username}_export_{timestamp}.html")

        self.manager.load()
        metadata = self.manager._metadata
        stats = self._get_stats()

        # Générer HTML
        html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Export - {self.username}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .stat-value {{
            font-size: 24px;
            font-weight: bold;
            color: #333;
        }}
        .stat-label {{
            color: #666;
            font-size: 14px;
        }}
        table {{
            width: 100%;
            background: white;
            border-collapse: collapse;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        th {{
            background: #4CAF50;
            color: white;
            padding: 12px;
            text-align: left;
        }}
        td {{
            padding: 10px;
            border-bottom: 1px solid #ddd;
        }}
        tr:hover {{
            background: #f5f5f5;
        }}
        .success {{ color: green; }}
        .failed {{ color: red; }}
        .video {{ background: #e3f2fd; }}
        .slideshow {{ background: #fff3e0; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Export TikTok - @{self.username}</h1>
        <p>Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}</p>
    </div>

    <div class="stats">
        <div class="stat-card">
            <div class="stat-value">{stats['total']}</div>
            <div class="stat-label">Total</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{stats['video']['count']}</div>
            <div class="stat-label">Vidéos</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{stats['slideshow']['count']}</div>
            <div class="stat-label">Slideshows</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{round(stats['total_size_mb'], 1)} MB</div>
            <div class="stat-label">Taille totale</div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Date</th>
                <th>Taille</th>
                <th>Fichiers</th>
                <th>Statut</th>
                <th>URL</th>
            </tr>
        </thead>
        <tbody>
"""

        # Ajouter les lignes
        for video_id, data in sorted(metadata.items(), key=lambda x: x[1].get('date', ''), reverse=True):
            item_type = data.get('type', 'video')
            success = data.get('success', True)
            size_mb = round(data.get('size', 0) / (1024 * 1024), 2)
            date_str = data.get('date', '')[:10] if data.get('date') else ''
            url = data.get('url', '')
            file_count = data.get('file_count', 1)

            status_class = 'success' if success else 'failed'
            status_text = 'Succès' if success else 'Échec'
            type_class = item_type

            html += f"""
            <tr class="{type_class}">
                <td>{video_id}</td>
                <td>{item_type.capitalize()}</td>
                <td>{date_str}</td>
                <td>{size_mb} MB</td>
                <td>{file_count}</td>
                <td class="{status_class}">{status_text}</td>
                <td><a href="{url}" target="_blank">Voir</a></td>
            </tr>
"""

        html += """
        </tbody>
    </table>
</body>
</html>
"""

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"Export HTML créé: {output_file}")
        return output_file

    def _get_stats(self):
        """Calcule les statistiques"""
        self.manager.load()
        metadata = self.manager._metadata

        stats = {
            'total': len(metadata),
            'video': {'count': 0, 'size': 0},
            'slideshow': {'count': 0, 'size': 0},
            'success': 0,
            'failed': 0,
            'total_size_mb': 0
        }

        for data in metadata.values():
            item_type = data.get('type', 'video')
            success = data.get('success', True)
            size = data.get('size', 0)

            stats[item_type]['count'] += 1
            stats[item_type]['size'] += size

            if success:
                stats['success'] += 1
            else:
                stats['failed'] += 1

        stats['total_size_mb'] = (stats['video']['size'] + stats['slideshow']['size']) / (1024 * 1024)

        return stats

    def export_all_formats(self):
        """
        Exporte dans tous les formats

        Returns:
            dict: Chemins des fichiers générés
        """
        return {
            'csv': self.export_to_csv(),
            'json': self.export_to_json(),
            'html': self.export_to_html()
        }


def export_user_data(username, format='csv', output_file=None):
    """
    Fonction helper pour exporter les données d'un utilisateur

    Args:
        username: Nom d'utilisateur
        format: Format d'export ('csv', 'json', 'html', 'all')
        output_file: Fichier de sortie (optionnel)

    Returns:
        str ou dict: Chemin(s) du/des fichier(s) généré(s)
    """
    exporter = DataExporter(username)

    if format == 'csv':
        return exporter.export_to_csv(output_file)
    elif format == 'json':
        return exporter.export_to_json(output_file)
    elif format == 'html':
        return exporter.export_to_html(output_file)
    elif format == 'all':
        return exporter.export_all_formats()
    else:
        raise ValueError(f"Format inconnu: {format}. Utilisez 'csv', 'json', 'html' ou 'all'")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python export_data.py <username> [format]")
        print("Formats: csv, json, html, all (défaut: csv)")
        sys.exit(1)

    username = sys.argv[1]
    format = sys.argv[2] if len(sys.argv) > 2 else 'csv'

    result = export_user_data(username, format)
    print(f"\nExport terminé!")
    if isinstance(result, dict):
        for fmt, path in result.items():
            print(f"  {fmt.upper()}: {path}")
    else:
        print(f"  Fichier: {result}")

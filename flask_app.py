from flask import Flask, render_template_string, request, redirect, url_for
from benford_scraper import scrape_for_benford, benford_analysis, benford_plot_png

app = Flask(__name__)

TEMPLATE = """
<!DOCTYPE html>
<html lang='es'>
<head>
  <meta charset='UTF-8'>
  <title>Benford Check Instagram</title>
  <style>
    body {font-family: Arial; margin: 20px; background:#f7f9fc;}
    table {border-collapse: collapse; width: 100%; margin-top: 1rem;}
    th, td {border:1px solid #ddd; padding:6px; font-size:14px;}
    th {background:#2d6cdf; color:#fff;}
    tr:nth-child(even){background:#eef3ff;}
    .ok {color:green; font-weight:bold;}
    .warn {color:#c77; font-weight:bold;}
    .chart {text-align:center; margin-top:2rem;}
    .badge {display:inline-block; padding:4px 8px; background:#2d6cdf; color:#fff; border-radius:4px; font-size:12px;}
  </style>
</head>
<body>
  <h1>Distribución Benford - Seguidores de seguidores</h1>
  <p>Se toma una muestra de los seguidores del perfil objetivo y se extrae el número de seguidores de cada uno. Luego se analiza el primer dígito.</p>
  <p class='badge'>Muestra: {{ sample_size }}</p>
  <div class='chart'>
    <img src='data:image/png;base64,{{ plot_png }}' alt='Benford Plot' />
  </div>
  <h2>Distribución Observada vs Esperada (%)</h2>
  <table>
    <thead>
      <tr><th>Dígito</th><th>Observado %</th><th>Benford %</th></tr>
    </thead>
    <tbody>
    {% for row in rows %}
      <tr>
        <td>{{ row.digit }}</td>
        <td>{{ '%.2f'|format(row.obs*100) }}</td>
        <td>{{ '%.2f'|format(row.exp*100) }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  <h2>Muestra cruda</h2>
  <table>
    <thead><tr><th>#</th><th>Usuario</th><th>Seguidores</th><th>Primer dígito</th></tr></thead>
    <tbody>
    {% for item in data %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>@{{ item.username }}</td>
        <td>{{ item.followers if item.followers is not none else 'N/A' }}</td>
        <td>{{ item.first_digit if item.first_digit is not none else '-' }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
</body>
</html>
"""

@app.route('/benford')
def benford():
  # Parámetros dinámicos ?limit=400&workers=20&mode=login|logout
  limit = request.args.get('limit', '9999')
  workers = request.args.get('workers', '3')
  mode = request.args.get('mode', 'login')
  try:
    limit_int = max(5, min(int(limit), 9999))  # rango seguro hasta 9999
  except:
    limit_int = 9999
  try:
    # Reducimos agresividad para evitar bloqueos: máximo 5
    workers_int = max(1, min(int(workers), 5))
  except:
    workers_int = 3
  counts_logged_out = (mode != 'login')
  results = scrape_for_benford(limit_users=limit_int, resume=True, counts_logged_out=counts_logged_out, max_workers=workers_int)
  analysis = benford_analysis(results)
  plot_png = benford_plot_png(analysis)
  rows = []
  for d in range(1,10):
    rows.append({'digit': d, 'obs': analysis['observed_pct'][d], 'exp': analysis['expected_pct'][d]})
  enriched = []
  for r in results:
    enriched.append({
      'username': r['username'],
      'followers': r['followers'],
      'first_digit': (str(r['followers'])[0] if r['followers'] else None)
    })
  return render_template_string(TEMPLATE,
                  rows=rows,
                  data=enriched,
                  sample_size=analysis['sample_size'],
                  plot_png=plot_png)

@app.route('/')
def index():
  # Redirige a /benford con valores por defecto para que no tengas que escribir la ruta completa
  # Workers reducido a 3 para evitar bloqueos de Instagram
  # Modo por defecto: login (usa sesión para contar followers)
  return redirect(url_for('benford', limit=9999, workers=3, mode='login'))

if __name__ == '__main__':
    # Iniciar servidor Flask
    app.run(host='0.0.0.0', port=5000, debug=True)

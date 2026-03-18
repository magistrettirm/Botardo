"""
backtest_temp.py
Backtest walk-forward del modelo de prediccion de ventas YPF.
Evalua modelo actual (40/60) vs modelo con factor YoY.
"""

import pyodbc
import sys
from datetime import date, timedelta
from collections import defaultdict

# ── Conexion ─────────────────────────────────────────────────────────────────

def get_conn():
    for driver in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"):
        try:
            return pyodbc.connect(
                f"DRIVER={{{driver}}};SERVER=192.168.200.44\\cloud;"
                f"DATABASE=Test_Rumaos;UID=itiersoper01;PWD=redMerco1234#;"
                f"TrustServerCertificate=yes;"
            )
        except pyodbc.Error:
            continue
    raise RuntimeError("No se pudo conectar al servidor SQL")

# ── Carga de datos ────────────────────────────────────────────────────────────

def cargar_ventas():
    print("Conectando al servidor SQL y descargando historial de ventas...")
    sql = """
        SELECT CAST(FECHASQL AS DATE) AS Fecha, UEN, CODPRODUCTO, SUM(Vol_Total) AS VolVenta
        FROM dbo.H_VentasPlayaMBC
        WHERE FECHASQL >= DATEADD(day, -400, GETDATE())
          AND FECHASQL < CAST(GETDATE() AS DATE)
          AND CODPRODUCTO <> 'GNC'
        GROUP BY CAST(FECHASQL AS DATE), UEN, CODPRODUCTO
        ORDER BY Fecha, UEN, CODPRODUCTO
    """
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()

    print(f"  Filas obtenidas: {len(rows)}")

    # {(uen, prod): [(fecha_str, litros), ...]}
    ventas = defaultdict(list)
    for r in rows:
        fecha = str(r.Fecha)
        uen   = (r.UEN or "").strip()
        prod  = (r.CODPRODUCTO or "").strip()
        if uen and prod:
            ventas[(uen, prod)].append((fecha, float(r.VolVenta or 0)))

    # Asegurar orden cronologico
    for k in ventas:
        ventas[k].sort(key=lambda x: x[0])

    return dict(ventas)

# ── Modelo de prediccion (replica db_pedidos.py) ──────────────────────────────

def predecir_venta(historial, fecha_objetivo, peso_5d=0.4, peso_sd=0.6):
    hist_antes = [(f, v) for f, v in historial if f < fecha_objetivo]
    if not hist_antes:
        return 0.0

    ultimos5 = [v for _, v in hist_antes[-5:]]
    avg_5d   = sum(ultimos5) / len(ultimos5)

    dia_semana = date.fromisoformat(fecha_objetivo).weekday()
    mismo_dia  = [v for f, v in hist_antes
                  if date.fromisoformat(f).weekday() == dia_semana][-4:]
    avg_sd = sum(mismo_dia) / len(mismo_dia) if mismo_dia else avg_5d

    return peso_5d * avg_5d + peso_sd * avg_sd

# ── Factor YoY ────────────────────────────────────────────────────────────────

def calcular_factor_yoy(historial, fecha_ref):
    """
    Ratio = avg ventas ultimas 4 semanas / avg mismas 4 semanas hace un año.
    fecha_ref: ultimo dia del historial disponible (exclusive del test).
    """
    fecha_ref_dt = date.fromisoformat(fecha_ref)

    # Ultimas 4 semanas (28 dias antes de fecha_ref)
    inicio_reciente = fecha_ref_dt - timedelta(days=28)
    ventas_recientes = [v for f, v in historial
                        if inicio_reciente <= date.fromisoformat(f) < fecha_ref_dt]

    # Mismo periodo hace un año
    inicio_anio_ant = inicio_reciente - timedelta(days=365)
    fin_anio_ant    = fecha_ref_dt   - timedelta(days=365)
    ventas_anio_ant = [v for f, v in historial
                       if inicio_anio_ant <= date.fromisoformat(f) < fin_anio_ant]

    if not ventas_recientes or not ventas_anio_ant:
        return 1.0

    avg_rec = sum(ventas_recientes) / len(ventas_recientes)
    avg_ant = sum(ventas_anio_ant)  / len(ventas_anio_ant)

    if avg_ant == 0:
        return 1.0

    ratio = avg_rec / avg_ant
    # Limitar entre 0.5 y 2.0 para evitar outliers extremos
    return max(0.5, min(2.0, ratio))

# ── Backtest walk-forward ─────────────────────────────────────────────────────

def backtest(ventas, dias_test=60, dias_historial=70):
    """
    Walk-forward sobre los ultimos `dias_test` dias.
    Para cada dia del test, usa solo los `dias_historial` dias previos.
    Retorna resultados por (uen, prod) y por dia de semana.
    """
    hoy = date.today()
    inicio_test = hoy - timedelta(days=dias_test)

    resultados_base = []   # (uen, prod, fecha, real, pred_base)
    resultados_yoy  = []   # (uen, prod, fecha, real, pred_yoy)

    claves = sorted(ventas.keys())
    print(f"\nEjecutando backtest walk-forward ({dias_test} dias de test, {dias_historial} dias de historial)...")
    print(f"  Combinaciones (UEN, producto): {len(claves)}")

    for clave in claves:
        hist_completo = ventas[clave]

        # Filtrar dias de test
        fechas_test = [f for f, _ in hist_completo if date.fromisoformat(f) >= inicio_test]

        for fecha_test in fechas_test:
            # Historial disponible ANTES del dia de test
            hist_prev = [(f, v) for f, v in hist_completo if f < fecha_test]

            # Limitar a dias_historial dias previos
            if hist_prev:
                corte = str(date.fromisoformat(fecha_test) - timedelta(days=dias_historial))
                hist_ventana = [(f, v) for f, v in hist_prev if f >= corte]
            else:
                hist_ventana = []

            # Venta real
            real = next((v for f, v in hist_completo if f == fecha_test), None)
            if real is None:
                continue

            # Prediccion base (pesos fijos 0.4 / 0.6)
            pred_base = predecir_venta(hist_ventana, fecha_test, 0.4, 0.6)

            # Factor YoY (calculado con historial previo al dia de test)
            if hist_prev:
                ultimo_hist = hist_prev[-1][0]
                factor_yoy = calcular_factor_yoy(hist_prev, ultimo_hist)
            else:
                factor_yoy = 1.0

            pred_yoy = pred_base * factor_yoy

            uen, prod = clave
            resultados_base.append((uen, prod, fecha_test, real, pred_base))
            resultados_yoy.append((uen, prod, fecha_test, real, pred_yoy))

    return resultados_base, resultados_yoy

# ── Calculo de metricas ───────────────────────────────────────────────────────

def calcular_metricas(resultados):
    """Calcula MAE y MAPE global, por (uen, prod), y por dia de semana."""
    # Global
    errores_abs  = [abs(pred - real) for _, _, _, real, pred in resultados]
    errores_pct  = [abs(pred - real) / real * 100 for _, _, _, real, pred in resultados if real > 0]
    mae_global   = sum(errores_abs) / len(errores_abs) if errores_abs else 0
    mape_global  = sum(errores_pct) / len(errores_pct) if errores_pct else 0

    # Por (uen, prod)
    por_clave = defaultdict(list)
    for uen, prod, fecha, real, pred in resultados:
        por_clave[(uen, prod)].append((real, pred))

    metricas_clave = {}
    for clave, pares in por_clave.items():
        errs = [abs(p - r) for r, p in pares]
        pcts = [abs(p - r) / r * 100 for r, p in pares if r > 0]
        metricas_clave[clave] = {
            "mae":  sum(errs) / len(errs) if errs else 0,
            "mape": sum(pcts) / len(pcts) if pcts else 0,
            "n":    len(pares),
        }

    # Por dia de semana
    DIAS = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
    por_dia = defaultdict(list)
    for _, _, fecha, real, pred in resultados:
        dow = date.fromisoformat(fecha).weekday()
        por_dia[dow].append(abs(pred - real))

    metricas_dia = {}
    for dow, errs in por_dia.items():
        metricas_dia[DIAS[dow]] = sum(errs) / len(errs) if errs else 0

    return mae_global, mape_global, metricas_clave, metricas_dia

# ── Reporte ───────────────────────────────────────────────────────────────────

def imprimir_reporte(res_base, res_yoy):
    mae_b, mape_b, por_clave_b, por_dia_b = calcular_metricas(res_base)
    mae_y, mape_y, por_clave_y, por_dia_y = calcular_metricas(res_yoy)

    mejora_pct = (mae_b - mae_y) / mae_b * 100 if mae_b > 0 else 0

    print("\n" + "=" * 70)
    print("REPORTE DE BACKTEST - MODELO DE PREDICCION DE VENTAS YPF")
    print("=" * 70)

    print(f"\n{'MODELO ACTUAL (40% ultimos5d / 60% mismo dia semana)':}")
    print(f"  MAE  total:  {mae_b:>10,.1f} litros")
    print(f"  MAPE total:  {mape_b:>10.2f}%")

    print(f"\n{'MODELO CON FACTOR INTERANUAL (YoY)':}")
    print(f"  MAE  total:  {mae_y:>10,.1f} litros")
    print(f"  MAPE total:  {mape_y:>10.2f}%")

    print(f"\n{'DIFERENCIA':}")
    print(f"  Reduccion MAE:  {mejora_pct:>+.2f}%  ({'MEJORA' if mejora_pct >= 0 else 'EMPEORA'})")
    umbral_implementar = mejora_pct >= 5.0
    print(f"  Umbral 5%:      {'SI - se implementa el cambio' if umbral_implementar else 'NO - no se implementa'}")

    print(f"\n{'MAE POR (UEN, PRODUCTO) - MODELO ACTUAL':}")
    print(f"  {'UEN':<20} {'Prod':<6} {'N':>5} {'MAE':>10} {'MAPE':>8}")
    print(f"  {'-'*55}")
    for clave in sorted(por_clave_b.keys()):
        m = por_clave_b[clave]
        m_y = por_clave_y.get(clave, {})
        print(f"  {clave[0]:<20} {clave[1]:<6} {m['n']:>5} {m['mae']:>10,.1f} {m['mape']:>7.1f}%"
              f"  ->  YoY MAE: {m_y.get('mae', 0):>10,.1f}")

    print(f"\n{'MAE POR DIA DE SEMANA - MODELO ACTUAL':}")
    for dia, mae in sorted(por_dia_b.items(), key=lambda x: x[1], reverse=True):
        yoy_mae = por_dia_y.get(dia, 0)
        print(f"  {dia:<12}:  MAE base {mae:>10,.1f}  ->  YoY {yoy_mae:>10,.1f}")

    peor_dia = max(por_dia_b, key=por_dia_b.get) if por_dia_b else "N/A"
    print(f"\n  Dia con mayor error: {peor_dia}")

    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)
    if mejora_pct >= 5.0:
        print(f"  El factor interanual reduce el MAE en {mejora_pct:.2f}%.")
        print("  Se IMPLEMENTARAN los cambios en db_pedidos.py.")
    elif mejora_pct > 0:
        print(f"  El factor interanual reduce el MAE en {mejora_pct:.2f}% (menor al umbral del 5%).")
        print("  No se implementa el cambio. La mejora es insuficiente para justificar la complejidad.")
    else:
        print(f"  El factor interanual EMPEORA el MAE en {abs(mejora_pct):.2f}%.")
        print("  No se implementa el cambio.")

    return umbral_implementar, mae_b, mape_b, mae_y, mape_y, mejora_pct, por_clave_b, por_dia_b

# ── Ejecucion ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ventas = cargar_ventas()
    res_base, res_yoy = backtest(ventas, dias_test=60, dias_historial=70)
    print(f"  Observaciones en test: {len(res_base)}")
    resultado = imprimir_reporte(res_base, res_yoy)
    implementar = resultado[0]
    sys.exit(0 if implementar else 1)

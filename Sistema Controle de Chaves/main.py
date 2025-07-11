from flask import Flask, jsonify, request
from flask_mysqldb import MySQL
from datetime import datetime
from flask_cors import CORS
from flask import send_file, request, make_response
from io import BytesIO
from xhtml2pdf import pisa


app = Flask(__name__)
CORS(app)

# Configuração do MySQL
app.config['MYSQL_HOST'] = '10.64.46.77'  # substitua pelo seu host
app.config['MYSQL_PORT'] = 3306  # substitua pela sua porta
app.config['MYSQL_USER'] = 'admin'  # substitua pelo seu usuário
app.config['MYSQL_PASSWORD'] = 'senac123'  # substitua pela sua senha
app.config['MYSQL_DB'] = 'Controle_Chaves'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

@app.route('/')
def index():
    return "API do Sistema de Controle de Chaves"

# -------------------------------
# UTILITÁRIOS DE PDF
# -------------------------------

def gerar_pdf(html):
    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf)
    if pisa_status.err:
        return None
    pdf.seek(0)
    return pdf

# Função para montar filtro de data conforme período
def filtro_data(periodo):
    from datetime import datetime, timedelta

    hoje = datetime.now()
    if periodo == 'dia':
        data_inicio = hoje.replace(hour=0, minute=0, second=0, microsecond=0)
    elif periodo == 'semana':
        data_inicio = hoje - timedelta(days=hoje.weekday())  # início da semana (segunda)
        data_inicio = data_inicio.replace(hour=0, minute=0, second=0, microsecond=0)
    elif periodo == 'mes':
        data_inicio = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif periodo == 'bimestre':
        mes_inicio = ((hoje.month - 1) // 2) * 2 + 1  # ex: se mês=7, bimestre começa em 7
        data_inicio = hoje.replace(month=mes_inicio, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif periodo == 'trimestre':
        mes_inicio = ((hoje.month - 1) // 3) * 3 + 1
        data_inicio = hoje.replace(month=mes_inicio, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        # padrão: mês
        data_inicio = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    return data_inicio

# -------------------------------
# UTILITÁRIOS DE CONSULTA
# -------------------------------

def chave_em_uso(id_chave):
    cur = mysql.connection.cursor()
    query = """
        SELECT 1 FROM tb_retiradas r
        LEFT JOIN tb_registro_geral rg ON rg.fk_id_retirada = r.id_retirada
        WHERE r.fk_id_chave = %s AND rg.fk_id_devolucao IS NULL
    """
    cur.execute(query, (id_chave,))
    result = cur.fetchone()
    cur.close()
    return bool(result)

def professor_existe(id_professor):
    cur = mysql.connection.cursor()
    cur.execute("SELECT 1 FROM tb_professores WHERE id_professor = %s", (id_professor,))
    result = cur.fetchone()
    cur.close()
    return bool(result)

def chave_existe(id_chave):
    cur = mysql.connection.cursor()
    cur.execute("SELECT 1 FROM tb_chaves WHERE id_chave = %s", (id_chave,))
    result = cur.fetchone()
    cur.close()
    return bool(result)


# -------------------------------
# ROTAS DE CONSULTA
# -------------------------------

@app.route('/professores', methods=['GET'])
def get_professores():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM tb_professores")
    data = cur.fetchall()
    cur.close()
    return jsonify(data)

@app.route('/chaves/disponiveis', methods=['GET'])
def get_chaves_disponiveis():
    cur = mysql.connection.cursor()
    query = """
        SELECT c.* FROM tb_chaves c
        WHERE c.id_chave NOT IN (
            SELECT r.fk_id_chave FROM tb_retiradas r
            JOIN tb_registro_geral rg ON r.id_retirada = rg.fk_id_retirada
            WHERE rg.fk_id_devolucao IS NULL
        )
    """
    cur.execute(query)
    data = cur.fetchall()
    cur.close()
    return jsonify(data)

@app.route('/chaves/retiradas', methods=['GET'])
def get_chaves_retiradas():
    cur = mysql.connection.cursor()
    query = """
        SELECT r.id_retirada, c.id_chave, c.descricao AS descricao_chave, 
               p.Nome_professor AS nome_professor, r.horario_retirada
        FROM tb_retiradas r
        JOIN tb_chaves c ON r.fk_id_chave = c.id_chave
        JOIN tb_professores p ON r.fk_id_professor = p.id_professor
        JOIN tb_registro_geral rg ON rg.fk_id_retirada = r.id_retirada
        WHERE rg.fk_id_devolucao IS NULL
    """
    cur.execute(query)
    data = cur.fetchall()
    cur.close()
    return jsonify(data)

@app.route('/historico', methods=['GET'])
def get_historico():
    cur = mysql.connection.cursor()
    query = """
        SELECT p.Nome_professor AS nome_professor, c.descricao AS descricao_chave,
               r.horario_retirada, d.horario_devolucao
        FROM tb_registro_geral rg
        JOIN tb_professores p ON rg.fk_id_professor = p.id_professor
        JOIN tb_retiradas r ON rg.fk_id_retirada = r.id_retirada
        JOIN tb_chaves c ON r.fk_id_chave = c.id_chave
        LEFT JOIN tb_devolucoes d ON rg.fk_id_devolucao = d.id_devolucao
        ORDER BY r.horario_retirada DESC
    """
    cur.execute(query)
    data = cur.fetchall()
    cur.close()
    return jsonify(data)

# -------------------------------
# ROTAS DE AÇÃO
# -------------------------------

# Função auxiliar para gerar PDF a partir de HTML

@app.route('/historico/pdf', methods=['GET'])
def historico_pdf():
    periodo = request.args.get('periodo', 'mes').lower()

    data_inicio = filtro_data(periodo)

    cur = mysql.connection.cursor()

    query = """
        SELECT p.Nome_professor AS nome_professor, c.descricao AS descricao_chave,
               r.horario_retirada, d.horario_devolucao
        FROM tb_registro_geral rg
        JOIN tb_professores p ON rg.fk_id_professor = p.id_professor
        JOIN tb_retiradas r ON rg.fk_id_retirada = r.id_retirada
        JOIN tb_chaves c ON r.fk_id_chave = c.id_chave
        LEFT JOIN tb_devolucoes d ON rg.fk_id_devolucao = d.id_devolucao
        WHERE r.horario_retirada >= %s
        ORDER BY r.horario_retirada DESC
    """

    cur.execute(query, (data_inicio,))
    registros = cur.fetchall()
    cur.close()

    # Montar conteúdo HTML para o PDF
    html = """
    <html>
    <head>
        <style>
            h1 { text-align: center; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; }
            th, td { border: 1px solid #333; padding: 8px; text-align: left; }
            th { background-color: #eee; }
        </style>
    </head>
    <body>
        <h1>Histórico de Movimentações - Período: {}</h1>
        <table>
            <thead>
                <tr>
                    <th>Professor</th>
                    <th>Chave</th>
                    <th>Retirada</th>
                    <th>Devolução</th>
                    <th>Tempo (minutos)</th>
                </tr>
            </thead>
            <tbody>
    """.format(periodo.capitalize())

    from datetime import datetime

    for reg in registros:
        retirada = reg['horario_retirada']
        devolucao = reg['horario_devolucao']
        tempo = ''
        if devolucao:
            diff = int((devolucao - retirada).total_seconds() // 60)
            tempo = str(diff)
        html += f"""
            <tr>
                <td>{reg['nome_professor']}</td>
                <td>{reg['descricao_chave'] or '-'}</td>
                <td>{retirada.strftime('%d/%m/%Y %H:%M')}</td>
                <td>{devolucao.strftime('%d/%m/%Y %H:%M') if devolucao else 'Pendente'}</td>
                <td>{tempo}</td>
            </tr>
        """

    html += """
            </tbody>
        </table>
    </body>
    </html>
    """

    pdf = gerar_pdf(html)
    if not pdf:
        return jsonify({"error": "Erro ao gerar PDF"}), 500

    response = make_response(pdf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=historico_{periodo}.pdf'
    return response


@app.route('/retirar', methods=['POST'])
def retirar_chave():
    try:
        data = request.get_json()
        id_professor = int(data.get('id_professor'))
        id_chave = int(data.get('id_chave'))

        if not professor_existe(id_professor):
            return jsonify({"error": "Professor inválido"}), 400
        if not chave_existe(id_chave):
            return jsonify({"error": "Chave inválida"}), 400
        if chave_em_uso(id_chave):
            return jsonify({"error": "Chave já está em uso"}), 400

        horario = datetime.now()
        cur = mysql.connection.cursor()
        
        cur.execute("START TRANSACTION")

        cur.execute("""
            INSERT INTO tb_retiradas (fk_id_professor, fk_id_chave, horario_retirada)
            VALUES (%s, %s, %s)
        """, (id_professor, id_chave, horario))
        
        id_retirada = cur.lastrowid

        cur.execute("""
            INSERT INTO tb_registro_geral (fk_id_retirada, fk_id_professor)
            VALUES (%s, %s)
        """, (id_retirada, id_professor))

        mysql.connection.commit()
        cur.close()
        return jsonify({"success": True, "id_retirada": id_retirada})
    
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/devolver', methods=['POST'])
def devolver_chave():
    try:
        data = request.get_json()
        id_retirada = int(data.get('id_retirada'))
        id_professor = int(data.get('id_professor'))
        id_chave = int(data.get('id_chave'))

        horario = datetime.now()
        cur = mysql.connection.cursor()

        cur.execute("START TRANSACTION")

        cur.execute("""
            INSERT INTO tb_devolucoes (fk_id_retirada, fk_id_professor, fk_id_chave, horario_devolucao)
            VALUES (%s, %s, %s, %s)
        """, (id_retirada, id_professor, id_chave, horario))

        id_devolucao = cur.lastrowid

        cur.execute("""
            UPDATE tb_registro_geral
            SET fk_id_devolucao = %s
            WHERE fk_id_retirada = %s
        """, (id_devolucao, id_retirada))

        mysql.connection.commit()
        cur.close()
        return jsonify({"success": True})
    
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({"error": str(e)}), 500

# -------------------------------
# CRUD SIMPLES DE PROFESSORES
# -------------------------------

@app.route('/professor', methods=['POST'])
def add_professor():
    data = request.get_json()
    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO tb_professores (Nome_professor, Email_professor, fk_id_periodo)
        VALUES (%s, %s, %s)
    """, (data['nome'], data['email'], data['periodo_id']))
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})

@app.route('/professor/<int:id>', methods=['PUT', 'DELETE'])
def manage_professor(id):
    cur = mysql.connection.cursor()
    if request.method == 'PUT':
        data = request.get_json()
        cur.execute("""
            UPDATE tb_professores
            SET Nome_professor = %s, Email_professor = %s, fk_id_periodo = %s
            WHERE id_professor = %s
        """, (data['nome'], data['email'], data['periodo_id'], id))
        response = {"success": True}
    elif request.method == 'DELETE':
        cur.execute("DELETE FROM tb_professores WHERE id_professor = %s", (id,))
        response = {"success": True}
    mysql.connection.commit()
    cur.close()
    return jsonify(response)

if __name__ == '__main__':
    app.run(debug=True)

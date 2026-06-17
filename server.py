from fastapi import FastAPI, Depends, Header
from fastapi.middleware.cors import CORSMiddleware


from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from typing import List, Dict

from openai import OpenAI
from jose import jwt, JWTError
from datetime import datetime, timedelta

from dotenv import load_dotenv
import uvicorn
import os
import json
# Carregar variáveis de ambiente do arquivo .env
load_dotenv()
#uvicorn server:app --reload
# ===== APP =====
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== OPENAI =====
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ===== BANCO =====
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///banco.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
TOKEN_MINUTOS = int(os.getenv("TOKEN_MINUTOS", "60"))

pwd_context = CryptContext(schemes=["bcrypt"])

# ===== MODELOS =====
class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    password = Column(String)
    role = Column(String)

class Atividade(Base):
    __tablename__ = "atividades"
    id = Column(Integer, primary_key=True)
    titulo = Column(String)
    descricao = Column(Text)

class Resposta(Base):
    __tablename__ = "respostas"
    id = Column(Integer, primary_key=True)
    usuario = Column(String)
    atividade_id = Column(Integer)
    codigo = Column(Text)
    feedback = Column(Text)

Base.metadata.create_all(engine)

# ===== DB =====
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ===== SCHEMAS =====


class LoginData(BaseModel):
    email: EmailStr
    password: str


class RegisterData(BaseModel):
    email: EmailStr
    password: str
    role: str = "aluno"

class ChatData(BaseModel):
    pergunta: str
    codigo: str
    historico: List[Dict[str, str]] = []

class VozData(BaseModel):
    texto: str
    
class RespostaData(BaseModel):
    usuario: str
    atividade_id: int
    codigo: str

class AtividadeData(BaseModel):
    titulo: str
    descricao: str

def criar_token(email: str):
    expira = datetime.utcnow() + timedelta(minutes=TOKEN_MINUTOS)

    dados = {
        "sub": email,
        "exp": expira
    }

    return jwt.encode(dados, SECRET_KEY, algorithm=ALGORITHM)


def get_usuario_logado(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    if not authorization:
        return None

    try:
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")

        if not email:
            return None

        user = db.query(Usuario).filter(Usuario.email == email).first()
        return user

    except JWTError:
        return None
    
# ===== LOGIN =====
@app.post("/register")
def register(data: RegisterData, db: Session = Depends(get_db)):
    existe = db.query(Usuario).filter(Usuario.email == data.email).first()

    if existe:
        return {"erro": "email já cadastrado"}

    user = Usuario(
        email=data.email,
        password=pwd_context.hash(data.password),
        role=data.role
    )

    db.add(user)
    db.commit()

    return {"msg": "criado"}


@app.post("/login")
def login(data: LoginData, db: Session = Depends(get_db)):
    user = db.query(Usuario).filter(Usuario.email == data.email).first()

    if not user or not pwd_context.verify(data.password, user.password):
        return {"erro": "login inválido"}

    token = criar_token(user.email)

    return {
        "access_token": token,
        "role": user.role
    }

# ===== CHAT IA =====
@app.post("/chat")
def chat(data: ChatData, usuario: Usuario = Depends(get_usuario_logado)):
    
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "Você é uma professora universitária de programação em C++.\n"
                    "Fale como um humano real, leve e amigável.\n"
                    "Explique como em sala de aula.\n"
                    "Responda apenas sobre C++.\n"
                    "Nunca diga que é IA.\n"
                    "Faça respostas curtas e objetivas.\n"
                    "Use essa base de código:\n"
                    "#include <iostream>\n"
                    "using namespace std;\n"
                    "int main(){'codigo' }\n"
                    "Evite usar ** ou ```\n"
                    "Tente entender sempre qual assunto está sendo trabalhado pelo aluno (arrays, rand, string, etc.)"
                )
            }
        ]

        # histórico
        for msg in data.historico[-10:]:
            if "role" in msg and "content" in msg:
                messages.append(msg)

        messages.append({
            "role": "user",
            "content": f"{data.pergunta}\n\nCódigo do aluno:\n{data.codigo}"
        })

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages
        )

        return {"resposta": response.choices[0].message.content}

    except Exception as e:
        print("ERRO IA:", e)
        return {"resposta": "Erro na IA"}

# ===== IA CORREÇÃO =====
@app.post("/enviar_resposta")
def enviar_resposta(
    data: dict,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_logado)
):
    
    try:
        codigo = data.get("codigo")
        entrada = data.get("entrada", "")
        saida = data.get("saida", "")
        esperado = data.get("esperado", "")

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é uma professora de C++ corrigindo um aluno.\n"
                        "Seja direta e didática.\n"
                        "Explique o erro e como corrigir.\n"
                        "Se necessário, mostre a correção.\n"
                        "Considere entrada e saída.\n"
                        "Especifique o tipo do erro, se é um erro de sintaxe, lógica ou de conceito"
                    )
                },
                {
                    "role": "user",
                    "content": f"""
Código:
{codigo}

Entrada:
{entrada}

Saída atual:
{saida}

Saída esperada:
{esperado}
"""
                }
            ]
        )

        feedback = response.choices[0].message.content

        return {"feedback": feedback}

    except Exception as e:
        print(e)
        return {"feedback": "Erro ao corrigir"}

# ===== ATIVIDADES (SEU BANCO) =====
@app.post("/atividade")
def criar(data: AtividadeData, db: Session = Depends(get_db)):
    atv = Atividade(titulo=data.titulo, descricao=data.descricao)
    db.add(atv)
    db.commit()
    return {"msg": "criada"}

@app.get("/atividades")
def listar(db: Session = Depends(get_db)):
    return db.query(Atividade).all()

@app.get("/respostas")
def listar_respostas(db: Session = Depends(get_db)):
    return db.query(Resposta).all()

# ===== NOVO: LESSONS (DO FLASK) =====
LESSONS = [
    {
        "id": 1,
        "title": "Olá, Mundo!",
        "emoji": "👋",
        "description": "faça um programa que imprima 'Olá, Mundo!' na tela. dificuldade 0",
        "starter_code": "#include <iostream>\n using namespace std;\nint main(){\n}"
    },
    {
        "id": 2,
        "title": "soma de dois números",
        "emoji": "📦",
        "description": "faça um programa que some dois números. dificuldade 0",
        "starter_code": "#include <iostream>\n using namespace std;\nint main(){\n    int a, b, soma;\n}"
    },
    {
        "id": 3,
        "title": "subtração de dois números e verificação de resultado negativo",
        "emoji": "📦",
        "description": "faça um programa que subtraia dois números e verifique se o resultado é negativo ou positivo (utilize if). dificuldade 1",
        "starter_code": "#include <iostream>\n using namespace std;\nint main(){\n    int a, b, diferenca;\n}"
    },
    {
    "id": 4,
    "title": "Média de três números",
    "emoji": "📊",
    "description": "Faça um programa que leia três números e calcule a média. dificuldade 1",
    "starter_code": "#include <iostream>\nusing namespace std;\nint main(){\n    float n1, n2, n3, media;\n}"
},
{
    "id": 5,
    "title": "Par ou Ímpar",
    "emoji": "🔢",
    "description": "Faça um programa que leia um número inteiro e informe se ele é par ou ímpar. dificuldade 2",
    "starter_code": "#include <iostream>\nusing namespace std;\nint main(){\n    int numero;\n}"
},
{
    "id": 6,
    "title": "Maior de dois números",
    "emoji": "📈",
    "description": "Leia dois números e informe qual deles é o maior. dificuldade 2",
    "starter_code": "#include <iostream>\nusing namespace std;\nint main(){\n    int a, b;\n}"
},
{
    "id": 7,
    "title": "Tabuada",
    "emoji": "📋",
    "description": "Leia um número e mostre sua tabuada de 1 a 10 usando for. dificuldade 3",
    "starter_code": "#include <iostream>\nusing namespace std;\nint main(){\n    int numero;\n}"
},
{
    "id": 8,
    "title": "Contagem regressiva",
    "emoji": "⏳",
    "description": "Faça uma contagem regressiva de 10 até 0 utilizando while. dificuldade 3",
    "starter_code": "#include <iostream>\nusing namespace std;\nint main(){\n    int contador = 10;\n}"
},
{
    "id": 9,
    "title": "Calculadora simples",
    "emoji": "🧮",
    "description": "Leia dois números e uma operação (+, -, * ou /) e exiba o resultado. dificuldade 4",
    "starter_code": "#include <iostream>\nusing namespace std;\nint main(){\n    float a, b;\n    char op;\n}"
},
{
    "id": 10,
    "title": "Sistema de notas",
    "emoji": "🎓",
    "description": "Leia a nota de um aluno e informe se está aprovado, recuperação ou reprovado. dificuldade 4",
    "starter_code": "#include <iostream>\nusing namespace std;\nint main(){\n    float nota;\n}"
},
{
    "id": 11,
    "title": "Média de um vetor",
    "emoji": "📚",
    "description": "Leia 5 números, armazene em um vetor (array) e calcule a média dos valores. dificuldade 5",
    "starter_code": "#include <iostream>\nusing namespace std;\n\nint main(){\n    int numeros[5];\n    int soma = 0;\n\n}"
},
{
    "id": 12,
    "title": "Soma dos elementos de uma matriz",
    "emoji": "🔲",
    "description": "Leia os valores de uma matriz 3x3 e calcule a soma de todos os elementos. dificuldade 5",
    "starter_code": "#include <iostream>\nusing namespace std;\n\nint main(){\n    int matriz[3][3];\n    int soma = 0;\n\n}"
},
{
    "id": 13,
    "title": "Maior valor do vetor",
    "emoji": "📈",
    "description": "Leia 10 números em um vetor e encontre o maior valor armazenado. dificuldade 5",
    "starter_code": "#include <iostream>\nusing namespace std;\n\nint main(){\n    int numeros[10];\n\n}"
},
{
    "id": 14,
    "title": "Diagonal principal da matriz",
    "emoji": "🎯",
    "description": "Leia uma matriz 3x3 e exiba apenas os elementos da diagonal principal. dificuldade 5",
    "starter_code": "#include <iostream>\nusing namespace std;\n\nint main(){\n    int matriz[3][3];\n\n}"
}
]



@app.get("/lessons")
def get_lessons():
    return LESSONS

@app.get("/lesson/{lesson_id}")
def get_lesson(lesson_id: int):
    lesson = next((l for l in LESSONS if l["id"] == lesson_id), None)
    if not lesson:
        return {"erro": "Lição não encontrada"}
    return lesson

@app.post("/explicar_aula")
def explicar_aula(data: dict):
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é uma professora de C++ explicando uma aula.\n"
                        "nunca escreva ### , ```, `, ou qualquer marcação de código. escreva o código como se fosse um humano escrevendo, sem formatação especial.\n"
                        "Explique de forma simples, didática e objetiva.\n"
                        "Use linguagem humana.\n"
                        "Pode usar exemplos simples.\n"
                        "nunca de a resposta da atividade solicitada, apenas explique o conteúdo da aula.\n"
                        "Não diga que é IA.\n"
                        "sempre assuma q o codigo ja usa 'using namespace std;'.\n"
                        "cada atividade tem uma dificuldade na descrição dela. representada de 0 a 5. 0 é muito fácil, 5 é muito difícil. Considere isso para explicar a aula de forma mais detalhada ou mais simples.\n"
                    )
                },
                {
                    "role": "user",
                    "content": f"""
                    Aula: {data.get("titulo")}
                    Descrição: {data.get("descricao")}
                    """
                }
            ]
        )

        return {"explicacao": response.choices[0].message.content}

    except Exception as e:
        print(e)
        return {"explicacao": "Erro ao explicar aula"}
  
    # ===== COMPILADOR IA =====
@app.post("/run")
def run_codigo(data: dict):

    codigo_cpp = data.get("codigo", "")

    prompt = f"""
Você é um simulador de compilador C++.

Analise o código abaixo e responda SOMENTE em JSON válido.

Formato obrigatório:
{{
  "status": "roda" ou "nao_roda",
  "terminal": "texto que apareceria no terminal"
}}

Regras:
- Se o código tiver erro de compilação, status = "nao_roda".
- Em "terminal", coloque mensagem semelhante ao g++.
- Se compilar, status = "roda".
- Simule a execução.
- Não explique fora do JSON.

Código C++:
{codigo_cpp}
"""

    try:

        resposta = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Você responde apenas JSON válido."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={"type": "json_object"},
            temperature=0
        )

        conteudo = resposta.choices[0].message.content

        resultado = json.loads(conteudo)

        return resultado

    except Exception as e:
        print(e)

        return {
            "status": "nao_roda",
            "terminal": "Erro interno do compilador"
        }
    

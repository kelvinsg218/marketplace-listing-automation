# Plano de evolução para SaaS

**Decisão atual:** terminar e validar o aplicativo Windows primeiro (auditoria de 19/10/2026). Nenhuma migração para
web começa sem aprovação. Este plano diz o que reaproveitar e em que ordem, se os pilotos justificarem.

## Por que não agora
- A automação usa o navegador já autenticado do usuário (perfis do Edge por conta); na web isso exigiria navegadores
  remotos por cliente, com custo e riscos de segurança maiores.
- Catálogos chegam com centenas de fotos; no desktop não há upload nem armazenamento pago.
- Ainda falta validar a publicação real e medir o ganho de tempo em pilotos.

## O que já está pronto para reaproveitar
| Camada | Situação |
|---|---|
| Importação (leitores, mapeamento, plano, gravação) | Sem dependência de interface; testada com pytest puro |
| Catálogo, histórico, edição em lote, anúncios, exportação | Serviços sem Qt; mesma regra de negócio serviria uma API |
| Banco | SQLite com migrações versionadas; esquema portável para PostgreSQL |
| Isolamento por empresa | Uma pasta por empresa; na web vira um "tenant" com banco ou esquema próprio |

## Etapas sugeridas
1. **Validar o desktop** com 2 ou 3 pilotos supervisionados e medir tempo e qualidade.
2. **Integração oficial** com o Mercado Livre (aplicativo registrado + OAuth do vendedor), que já funciona por API e
   não depende de navegador: é o primeiro pedaço que faz sentido no servidor.
3. **API interna** (FastAPI, por exemplo) expondo os serviços atuais, ainda com o app desktop como cliente.
4. **Painel web** para importação, revisão e exportação; fotos em armazenamento de objetos; desktop continua para
   automação por navegador, se ainda for necessária.
5. **Cobrança e licenças** com chaves assinadas ou servidor de licenças; termos de uso e privacidade (LGPD).

## Riscos e custos a avaliar antes
- Armazenamento e tráfego de imagens por cliente.
- Responsabilidade por dados de terceiros (LGPD), backups e retenção.
- Dependência das regras e limites das APIs oficiais dos marketplaces.

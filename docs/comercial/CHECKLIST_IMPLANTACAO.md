# Checklist de implantação de um piloto supervisionado

## Antes (sem o cliente)
- [ ] Instalar o `MLA-Setup-<versão>.exe` num **computador limpo** (sem Python) e seguir o
      [roteiro do segundo computador](../ROTEIRO_TESTE_SEGUNDO_COMPUTADOR.md): a instalação em máquina limpa
      ainda não foi comprovada.
- [ ] Conferir o SHA-256 do pacote enviado ao cliente.
- [ ] Rodar a demonstração de 5 minutos com dados fictícios na máquina que será usada.
- [ ] Combinar por escrito: dados ficam no computador do cliente; o MLA não publica nada sozinho; publicação real
      direta no marketplace não faz parte do piloto.

## Com o cliente: preparação
- [ ] Criar uma empresa no MLA para o cliente (não usar a "Empresa principal" de demonstração).
- [ ] Receber uma amostra da base do fornecedor (50 a 300 produtos) **e** as fotos.
- [ ] Anotar como o cliente faz hoje: quem cadastra, quanto tempo leva por produto, onde estão os erros comuns.
      Sem essa medição não é possível falar em economia de tempo.
- [ ] Criar backup (Configurações → Criar backup agora) antes da primeira importação.

## Durante
- [ ] Importar a base; salvar o mapeamento como modelo do fornecedor.
- [ ] Associar a pasta de fotos.
- [ ] Gerar o relatório de pendências e devolver ao cliente/fornecedor.
- [ ] Corrigir em lote apenas campos descritivos combinados com o cliente.
- [ ] Preparar e revisar anúncios com o cliente; aprovar só o que ele conferiu.
- [ ] Exportar a planilha intermediária e copiar, com o cliente, para o modelo oficial baixado na conta dele.
- [ ] Registrar tempos (início/fim de cada etapa) e problemas no modelo de relatório.

## Se o cliente quiser testar a conta real do marketplace
- [ ] Autorização escrita do dono da conta.
- [ ] Login feito pela própria pessoa no navegador dedicado do MLA; CAPTCHA e verificações sempre manuais.
- [ ] Apenas leitura (abrir a área de anúncios, ver o formulário). Nenhum anúncio criado, editado ou publicado
      sem um roteiro de validação aprovado à parte.

## Depois
- [ ] Preencher o [modelo de relatório de piloto](MODELO_RELATORIO_PILOTO.md) com números medidos.
- [ ] Aplicar o [modelo de feedback](MODELO_FEEDBACK.md).
- [ ] Entregar ao cliente a planilha, o relatório de pendências e um backup.
- [ ] Combinar o destino dos dados ao fim do piloto (manter, exportar ou apagar com
      `desinstalar.cmd -RemoverDados -ConfirmarRemocaoDeDados`).

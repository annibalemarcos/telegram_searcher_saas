import asyncio
import re
from telethon import TelegramClient
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.functions.messages import SearchGlobalRequest
from telethon.tl.types import ChannelParticipantsSearch, InputMessagesFilterEmpty, InputPeerEmpty
import logging
from datetime import datetime

# Importação para detecção de idioma
try:
    from langdetect import detect, LangDetectException
except ImportError:
    print("Biblioteca 'langdetect' não encontrada. Por favor, instale com: pip install langdetect")
    exit()

# Configurações da API (mantenha as suas)
API_ID = 20041297
API_HASH = "ba389b89510d524e1f62da82cc24c266"

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TelegramGroupSearcher:
    def __init__(self, api_id, api_hash, phone_number):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone_number = phone_number
        self.client = TelegramClient(f'session_{phone_number}', api_id, api_hash)
        
        # NOVO: Armazena os IDs dos grupos que o usuário já participa
        self.my_group_ids = set()
        
        # Dicionário para armazenar as preferências de filtro do usuário
        self.filters = {
            'language': None,
            'min_members': 0,
            'max_members': None,
            'group_type': 'all',  # 'all', 'groups', 'channels'
            'verified_only': False,
            # NOVO: Padrão para excluir grupos que já participa
            'exclude_my_groups': True 
        }

    async def get_my_dialog_ids(self):
        """Obtém os IDs de todos os grupos e canais que o usuário já participa."""
        logger.info("Carregando lista de grupos/canais atuais para exclusão...")
        async for dialog in self.client.iter_dialogs():
            # Verifica se é um grupo ou canal
            if dialog.is_group or dialog.is_channel:
                self.my_group_ids.add(dialog.id)
        logger.info(f"Você já participa de {len(self.my_group_ids)} grupos/canais. Estes serão excluídos das buscas.")

    async def connect(self):
        """Conecta ao Telegram e carrega os grupos atuais"""
        try:
            await self.client.start(phone=self.phone_number)
            logger.info("Conectado ao Telegram com sucesso!")
            
            # NOVO: Após conectar, carrega a lista de grupos atuais
            await self.get_my_dialog_ids()
            
            return True
        except Exception as e:
            logger.error(f"Erro ao conectar: {e}")
            return False

    def is_language(self, group_info, lang_code='pt'):
        """Verifica se o idioma do grupo corresponde ao código fornecido (ex: 'pt' para português)"""
        text_to_check = (group_info.get('title', '') + ' ' + group_info.get('description', '')).strip()
        if not text_to_check:
            return False
        
        # Limpa o texto para melhorar a detecção
        text_to_check = re.sub(r'[^A-Za-zÀ-ÿ\s]', '', text_to_check) # Inclui acentos para pt-br
        if len(text_to_check) < 20: 
            return False # Texto muito curto para detectar com precisão
            
        try:
            detected_lang = detect(text_to_check)
            return detected_lang == lang_code
        except LangDetectException:
            return False

    async def apply_filters(self, groups):
        """Aplica os filtros definidos pelo usuário aos resultados da busca"""
        filtered_groups = []
        logger.info(f"Aplicando filtros em {len(groups)} resultados...")

        for group in groups:
            
            # NOVO: 0. Excluir grupos que já participo
            if self.filters['exclude_my_groups'] and group['id'] in self.my_group_ids:
                continue

            # 1. Filtro por número de membros
            participants = group.get('participants_count', 0)
            if self.filters['min_members'] and participants < self.filters['min_members']:
                continue
            if self.filters['max_members'] and participants > self.filters['max_members']:
                continue

            # 2. Filtro por tipo (grupo vs canal)
            group_type = group.get('type', 'channel')
            if self.filters['group_type'] == 'groups' and 'group' not in group_type:
                continue
            if self.filters['group_type'] == 'channels' and 'channel' != group_type:
                continue
            
            # 3. Filtro por status de verificado
            if self.filters['verified_only'] and not group.get('verified', False):
                continue
                
            # 4. Filtro de Idioma
            if self.filters['language'] and not self.is_language(group, self.filters['language']):
                continue

            filtered_groups.append(group)
            
        logger.info(f"Filtros aplicados. {len(filtered_groups)} resultados restantes.")
        return filtered_groups

    def _create_group_info_dict(self, entity, method):
        """Cria um dicionário padronizado com informações da entidade (grupo/canal)"""
        group_type = 'channel'
        if getattr(entity, 'megagroup', False):
            group_type = 'supergroup'
        elif hasattr(entity, 'broadcast') and not getattr(entity, 'broadcast', True):
             group_type = 'group'

        return {
            'id': entity.id,
            'title': entity.title,
            'username': getattr(entity, 'username', None),
            'participants_count': getattr(entity, 'participants_count', 0) or 0,
            'type': group_type,
            'verified': getattr(entity, 'verified', False),
            'description': getattr(entity, 'about', '') or '',
            'method': method
        }

    async def search_groups(self, keyword, limit=50):
        """Busca grupos públicos por palavra-chave usando múltiplos métodos"""
        try:
            logger.info(f"Buscando globalmente com a palavra-chave: '{keyword}'")
            groups = []
            seen_ids = set()

            # Função auxiliar para adicionar grupos evitando duplicatas na busca bruta
            def add_group(entity, method):
                if entity.id not in seen_ids:
                    # Só faz sentido buscar globalmente se tiver username (público)
                    if hasattr(entity, 'username') and entity.username:
                        group_info = self._create_group_info_dict(entity, method)
                        groups.append(group_info)
                        seen_ids.add(entity.id)

            # Método 1: Busca global de mensagens públicas (encontra grupos onde a palavra foi mencionada)
            try:
                logger.info("Tentando busca global de mensagens...")
                result = await self.client(SearchGlobalRequest(
                    q=keyword,
                    filter=InputMessagesFilterEmpty(),
                    min_date=datetime(2000, 1, 1),   # início amplo
                    max_date=datetime.now(),         # até agora
                    limit=limit,
                    offset_rate=0,
                    offset_peer=InputPeerEmpty(),
                    offset_id=0
                ))
                
                # Processa os chats encontrados pela busca global
                for chat in result.chats:
                    add_group(chat, 'global_messages_chats')

            except Exception as e:
                logger.warning(f"Erro na busca global de mensagens: {e}")

            # Método 2: Busca direta por contatos/chats públicos (busca no título/username)
            try:
                logger.info("Tentando busca de contatos (SearchRequest)...")
                result = await self.client(SearchRequest(q=keyword, limit=limit))
                for chat in result.chats:
                    add_group(chat, 'contacts_search')
            except Exception as e:
                logger.warning(f"Erro na busca de contatos: {e}")

            # Método 3: Variações do username (busca direta)
            if len(keyword) > 3:
                variations = [keyword.replace(' ', '_'), keyword.replace(' ', '')]
                # Adiciona variações comuns em português se o filtro estiver ativo
                if self.filters['language'] == 'pt':
                     variations.extend([f"{keyword}_br", f"{keyword}_brasil", f"{keyword}oficial"])
                
                for variation in variations:
                    try:
                        # Remove o @ se o usuário digitou
                        username = variation.lstrip('@')
                        entity = await self.client.get_entity(username)
                        if hasattr(entity, 'megagroup') or hasattr(entity, 'broadcast'):
                            add_group(entity, 'variation_search')
                    except Exception:
                        continue
            
            # Ordenar por número de participantes
            groups.sort(key=lambda x: x.get('participants_count', 0), reverse=True)
            logger.info(f"Total de grupos públicos encontrados antes da filtragem: {len(groups)}")
            return groups
        except Exception as e:
            logger.error(f"Erro na busca: {e}")
            return []

    async def display_results(self, groups):
        """Exibe os resultados da busca"""
        if not groups:
            print("\nNenhum grupo novo encontrado com os filtros atuais.")
            print("\nDicas para melhorar a busca:")
            print("• Tente palavras-chave mais genéricas.")
            print("• Simplifique ou remova os filtros (especialmente o de idioma).")
            return

        print(f"\n=== RESULTADOS DA BUSCA ({len(groups)} NOVOS GRUPOS/CANAIS) ===")
        print("-" * 70)
        
        for i, group in enumerate(groups, 1):
            print(f"\n{i}. {group['title']} {'✅' if group.get('verified') else ''}")
            print(f"   - Tipo: {group['type'].capitalize()}")
            print(f"   - Username: @{group['username']}" if group['username'] else "   - Username: N/A")
            print(f"   - Participantes: {group.get('participants_count', 0):,}")
            if group['username']:
                print(f"   - Link: https://t.me/{group['username']}")
            
            desc = group.get('description', '')
            if desc:
                # Melhora a exibição da descrição, removendo quebras de linha excessivas
                desc_clean = ' '.join(desc[:150].splitlines())
                print(f"   - Descrição: {desc_clean}...")
            print("   " + "="*50)

    async def _get_search_filters(self):
        """Interface para o usuário definir as preferências de filtro."""
        print("\n--- Definir Filtros de Busca ---")
        
        # Filtro de Idioma
        lang_choice = input("Filtrar por idioma Português (pt-br)? [s/N]: ").lower().strip()
        self.filters['language'] = 'pt' if lang_choice == 's' else None
        if self.filters['language']:
            print(">> Filtro de idioma PT ativado. (Isso pode reduzir muito os resultados e tornar a busca mais lenta)")
        
        # Filtro de Tipo
        type_choice = input("Filtrar por tipo? [G]rupos / [C]anais / [A]mbos (padrão): ").lower().strip()
        if type_choice == 'g':
            self.filters['group_type'] = 'groups'
            print(">> Filtrando apenas por Grupos/Supergrupos.")
        elif type_choice == 'c':
            self.filters['group_type'] = 'channels'
            print(">> Filtrando apenas por Canais.")
        else:
            self.filters['group_type'] = 'all'
            print(">> Buscando por Grupos e Canais.")
            
        # Filtro de Membros
        try:
            min_mem = input("Número MÍNIMO de membros (padrão: 0): ").strip()
            self.filters['min_members'] = int(min_mem) if min_mem.isdigit() else 0
            if self.filters['min_members']: print(f">> Mínimo de {self.filters['min_members']:,} membros.")
            
            max_mem = input("Número MÁXIMO de membros (deixe em branco para ilimitado): ").strip()
            self.filters['max_members'] = int(max_mem) if max_mem.isdigit() else None
            if self.filters['max_members']: print(f">> Máximo de {self.filters['max_members']:,} membros.")
        except ValueError:
            print("Entrada de membros inválida. Usando valores padrão.")

        # Filtro de Verificado
        verified_choice = input("Buscar apenas canais/grupos VERIFICADOS? [s/N]: ").lower().strip()
        self.filters['verified_only'] = True if verified_choice == 's' else False
        
        # NOVO: Filtro de Exclusão de Meus Grupos
        exclude_choice = input("Excluir grupos que você já participa? [S/n]: ").lower().strip()
        self.filters['exclude_my_groups'] = False if exclude_choice == 'n' else True

        print("--- Filtros definidos! ---")


    async def interactive_search(self):
        """Modo interativo aprimorado para buscar grupos"""
        while True:
            print("\n=== BUSCA AVANÇADA DE GRUPOS NO TELEGRAM ===")
            print("Filtros Atuais:")
            print(f"  - Excluir meus grupos: {'Sim' if self.filters['exclude_my_groups'] else 'Não'}")
            print(f"  - Idioma: {self.filters['language'] or 'Qualquer'}")
            print(f"  - Tipo: {self.filters['group_type'].capitalize()}")
            print(f"  - Membros: Min {self.filters['min_members'] or 0}, Max {self.filters['max_members'] or 'Ilimitado'}")
            print(f"  - Apenas Verificados: {'Sim' if self.filters['verified_only'] else 'Não'}")
            print("-" * 20)
            print("Opções:")
            print("1. Buscar por palavra-chave (Usando filtros acima)")
            print("2. Alterar Filtros")
            print("3. Sair")
            
            choice = input("\nEscolha uma opção (1-3): ").strip()
            
            if choice == '1':
                keyword = input("Digite a palavra-chave para buscar: ").strip()
                if not keyword:
                    print("Por favor, digite uma palavra-chave válida.")
                    continue
                
                print(f"\nIniciando busca por '{keyword}'...")
                raw_results = await self.search_groups(keyword)
                filtered_results = await self.apply_filters(raw_results)
                await self.display_results(filtered_results)

            elif choice == '2':
                await self._get_search_filters()

            elif choice == '3':
                print("Encerrando...")
                break
                
            else:
                print("Opção inválida. Tente novamente.")

    async def disconnect(self):
        """Desconecta do Telegram"""
        await self.client.disconnect()
        logger.info("Desconectado do Telegram")


async def main():
    """Função principal"""
    phone_number = input("Digite seu número de telefone (com código do país, ex: +5511999999999): ").strip()
    if not phone_number:
        print("Número de telefone é obrigatório!")
        return
    
    searcher = TelegramGroupSearcher(API_ID, API_HASH, phone_number)
    
    # Conexão e carregamento inicial dos grupos do usuário
    if await searcher.connect():
        try:
            await searcher.interactive_search()
        except KeyboardInterrupt:
            print("\nInterrompido pelo usuário.")
        finally:
            await searcher.disconnect()
    else:
        print("Falha ao conectar ao Telegram. Verifique suas credenciais e o código de acesso.")

if __name__ == "__main__":
    print("=== TELEGRAM GROUP SEARCHER (v2.1 - Exclusão de Meus Grupos) ===")
    print("Buscando por grupos/canais públicos dos quais você ainda não participa.")
    print("=" * 65)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScript interrompido pelo usuário.")
    except Exception as e:
        print(f"Erro inesperado: {e}")
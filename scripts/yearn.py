import warnings
from dataclasses import dataclass
from typing import Optional, Union

from brownie import interface, web3
from brownie.network.contract import InterfaceContainer
from click import secho

from yearn import constants
from yearn import curve
from yearn import uniswap

warnings.simplefilter('ignore')


@dataclass
class Vault:
    vault: Union[str, InterfaceContainer]
    controller: Union[str, InterfaceContainer]
    token: Union[str, interface.ERC20]
    strategy: str
    is_wrapped: bool
    is_delegated: bool
    # the rest is populated in post init
    name: Optional[str] = None

    def __post_init__(self):
        self.vault = constants.VAULT_INTERFACES.get(self.vault, interface.yVault)(self.vault)
        self.controller = constants.CONTROLLER_INTERFACES[self.controller](self.controller)
        self.strategy = constants.STRATEGY_INTERFACES[self.strategy](self.strategy)
        self.token = interface.ERC20(self.token)
        self.name = self.vault.name()

    @property
    def scale(self):
        return 10 ** self.vault.decimals()


def load_registry(address='registry.ychad.eth'):
    return interface.YRegistry(address)


def load_vaults(registry):
    return [Vault(*params) for params in zip(registry.getVaults(), *registry.getVaultsInfo())]


def describe_vault(vault: Vault):
    info = {
        'vault balance': vault.vault.balance() / vault.scale,
        'share price': vault.vault.getPricePerFullShare() / 1e18,
        'vault total': vault.vault.totalSupply() / vault.scale,
        'strategy balance': vault.strategy.balanceOf() / vault.scale,
    }

    # some of the oldest vaults don't implement these methods
    if hasattr(vault.vault, 'available'):
        info['available'] = vault.vault.available() / vault.scale

    if hasattr(vault.vault, 'min') and hasattr(vault.vault, 'max'):
        info['strategy buffer'] = vault.vault.min() / vault.vault.max()

    # new curve voter proxy vaults
    if hasattr(vault.strategy, 'proxy'):
        strategy_proxy = interface.StrategyProxy(vault.strategy.proxy())
        vote_proxy = interface.CurveYCRVVoter(vault.strategy.voter())
        escrow = interface.CurveVotingEscrow(vote_proxy.escrow())
        swap = interface.CurveSwap(vault.strategy.curve())
        gauge = interface.CurveGauge(vault.strategy.gauge())
        info.update(curve.calculate_boost(gauge, vote_proxy))
        info.update(curve.calculate_apy(gauge, swap))

    return info


def exporter():
    registry = load_registry()
    vaults = load_vaults(registry)
    for i, vault in enumerate(vaults):
        # TODO: debug SBTC and BUSD for now
        if vault.vault not in (
            '0x2994529C0652D127b7842094103715ec5299bBed',
            '0x7Ff566E1d69DEfF32a7b244aE7276b9f90e9D0f6',
        ):
            continue

        secho(f'{i} {vault}', fg='green')
        secho(vault.name, fg='yellow')
        info = describe_vault(vault)
        for a, b in info.items():
            print(f'{a} = {b}')


def audit():
    """
    Audit vault and strategy configuration.
    """
    governance = web3.ens.resolve('ychad.eth')
    registry = load_registry()
    vaults = load_vaults(registry)
    for v in vaults:
        if v.vault.governance() != governance:
            secho(f'{v.name} vault governance == {v.vault.governance()}', fg='red')
            print(f'{v.vault}.setGovernance({governance})')
        if v.strategy.governance() != governance:
            secho(f'{v.name} strategy governance == {v.strategy.governance()}', fg='red')
            print(f'{v.strategy}.setGovernance({governance})')

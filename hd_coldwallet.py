import egulden
import sys
import argparse
import json
import math

## TODO: not working, fix bci.BlockchainInfo classes etc

is_python2 = str == bytes

if is_python2:
    from urllib2 import urlopen
else:
    from urllib.request import urlopen
    raw_input = input
    xrange = range


REQUIRE_OFFLINE = True
RUNNING_OFFLINE = None

def user_input(s, expectednotchar=None, readanyway=False):
    if not readanyway:
        sys.stderr.write(s)
    if not sys.stdin.isatty() and not readanyway:
        if expectednotchar:
            sys.stderr.write(expectednotchar)
        return expectednotchar
    q = raw_input()
    if expectednotchar and (q[0].lower() not in expectednotchar):
        quit()
    return q

def test_offline():
    global RUNNING_OFFLINE
    if RUNNING_OFFLINE is None:
        user_input("Make sure you are offline, alone, and your screen is not visible. [OK]\n")
        try:
            result = urlopen("https://google.com", timeout=3.0).read()
            user_input("You lied about being offline! [OK]")
            RUNNING_OFFLINE = False
            return False
        except Exception as e:
            RUNNING_OFFLINE = True
        finally:
            return True
    else:
        return RUNNING_OFFLINE


def offlineonly(f):	
    def wrapper(*args,**kwargs):
        global REQUIRE_OFFLINE
        if REQUIRE_OFFLINE:
            if not test_offline():
                user_input(
                    'Warning!  You are not in offline mode! ' +
                    'You should immediately quit before executing this function! ' +
                    'Do you want to do so now? [Y/n]', 'n'
                )
        return f(*args,**kwargs)
    return wrapper


@offlineonly
def get_password():
    mnemonic = user_input('Type your password mnemonic, one word at a time:\n', readanyway=True)
    return mnemonic

@offlineonly
def get_generated_words(entropy_amount = 128, entropy_selection = 'system'):
    if entropy_selection == 'system':
        return bitcoin.words_generate(num_bits_entropy = entropy_amount)
    else:
        cur_ent = 1
        max_ent = (1 << entropy_amount)
        cur_bits = 0
        user_input(
            'Enter randomness in the format "<1 to N>/<N>" until the total entropy is reached.. ' +
            'for example, rolling a 6-sided dice and getting a 4 would be "4/6" [OK]'
        )
        while cur_ent < max_ent:
            r = user_input("Entropy So Far/Entropy Needed: %f/%d.\nNext pair: " % (math.log(cur_ent)/math.log(2),entropy_amount)).split('/')
            v = int(r[0]) - 1
            b = int(r[1])
            cur_ent  *= b
            cur_bits *= b
            cur_bits += v
        return bitcoin.words_generate(num_bits_entropy = entropy_amount, randombits = lambda x: cur_bits)


def check_outputs_max_index(unspents, changecode=0):
    index =- 1
    for u in unspents:
        upath = u['xpub']['path']
        cdexpath = bitcoin.bip32_path_from_string(upath)
        if cdexpath[-2] == changecode:
            cdex = cdexpath[-1]
            index = max(cdex, index)
    return index + 1


def get_master_key():
    words=' '.join(get_password().split())
    try:
        a = bitcoin.words_verify(words)
    except Exception as e:
        print(e)
        a = False

    if not a:
        q = user_input(
            "Warning! Mnemonic does not verify as a string of bip39 english " +
            "space-seperated words! continue? [y/N]", 'y')

    seed = bitcoin.mnemonic_to_seed(words)
    master_key = bitcoin.bip32_master_key(seed)
    return master_key


def sign(args):
    master_key = get_master_key()

    input_transaction = json.load(args.input_file)
    privs = input_transaction['keys']
    tx = input_transaction['tx']
    for k, p in privs.items():
        pstr = bitcoin.bip32_path_from_string(p['path'])
        xpubk = p['m']
        a = 0
        priv_key = bitcoin.hd_lookup(master_key, account = a)
        while bitcoin.bip32_privtopub(priv_key) != xpubk:
            priv_key = bitcoin.hd_lookup(master_key, account = a)
        a += 1
        privs[k] = bitcoin.bip32_descend(priv_key, pstr[0], pstr[1])
    print(bitcoin.signall(str(tx), privs))
    #sign the transaction
    #print the hex


def privkey(args):
    master_key = get_master_key()

    if args.root or (args.account and args.account < 0):
        #print("The following is your master root extended public key:")
        print(master_key)
    else:
        account_privkey = bitcoin.hd_lookup(master_key,account=args.account)
        #print("The following is the extended public key for account #%d:" % (args.account))
        print(account_privkey)


def pubkey(args):
    master_key = get_master_key()

    if args.root or (args.account and args.account < 0):
        #print("The following is your master root extended public key:")
        print(bitcoin.bip32_privtopub(master_key))
    else:
        account_privkey = bitcoin.hd_lookup(master_key, account = args.account)
        #print("The following is the extended public key for account #%d:" % (args.account))
        print(bitcoin.bip32_privtopub(account_privkey))


def send(args):
    if len(args.outputs) % 2 != 0:
        raise Exception("When sending, there must be an even number of arguments " +
                        "for the outputs (address, price)")
    unspents = bitcoin.BlockchainInfo.unspent_xpub(args.xpub)
    def btctosatoshi(vs):
        return int(float(vs)*100000000.0)
    fee = btctosatoshi(args.fee)
    if fee < 0:
        fee = int(0.0001*100000000) #todo do something to estimated fee...make it negative or something though... DONT
    outaddrval = [(args.outputs[2*i],btctosatoshi(args.outputs[2*i+1])) for i in range(len(args.outputs)//2)]
    outtotalval = sum([o[1] for o in outaddrval])
    changeindex = check_outputs_max_index(unspents,1)
    changeaddress = bitcoin.pubtoaddr(bitcoin.bip32_descend(args.xpub, 1, changeindex))

    unspents = bitcoin.select(unspents, outtotalval+fee)
    #unspents cull using outtotalval
    unspenttotalval = sum([u['value'] for u in unspents])
    changeamount = unspenttotalval - (outtotalval + abs(fee))

    if changeamount < 0:
        raise Exception("There is unlikely to be enough unspent outputs to cover the transaction and fees")
    out = {}
    outs = outaddrval
    if changeamount > 0:
        outs += [[changeaddress, changeamount]]
    #print(unspents)
    #print(outs)
    otx = [{'address':o[0], 'value':o[1]} for o in outs]
    tx = bitcoin.mktx(unspents, otx)

    #compute all the underlying addresses and pubkeys into a string hash
    #estimate the fee
    #build the transaction
    out['tx'] = tx
    out['keys'] = dict([(u['output'], u['xpub']) for u in unspents])
    #print(bitcoin.deserialize(tx))
    json.dump(out, sys.stdout)


def address(args):
    c = 1 if args.change else 0
    if args.index < 0:
        unspents = bitcoin.BlockchainInfo.unspent_xpub(args.xpub)
        index = check_outputs_max_index(unspents, c)
    else:
        index=args.index
    address = bitcoin.pubtoaddr(bitcoin.bip32_descend(args.xpub, c, index))

    print(address)


def generate(args):
    print(' '.join(get_generated_words(args.entropy_bits, args.entropy_source)))


if __name__=="__main__":
    aparser = argparse.ArgumentParser()
    aparser.add_argument('--no_offline_check',action='store_true',help="Disable the check verifying that you are offline")

    subaparsers=aparser.add_subparsers()
    aparse_send = subaparsers.add_parser('send',help="[online] Get the unspents and generate an unsigned transaction to some outputs")
    aparse_send.add_argument('--xpub','-p',required=True,help="The xpubkey for the hdwallet account")
    aparse_send.add_argument('--fee','-f',default=-1,type=float,help="The fee to use")
    aparse_send.add_argument('outputs',help="The outputs, two at a time in <addr> <amount> format...e.g. 1L3qUmg3GeuGrGvi1JxT2jMhAdV76qVj7V 1.032",nargs='+')
    aparse_send.set_defaults(func=send)

    aparse_pubkey = subaparsers.add_parser('pubkey',help='[offline] Get the extended HD pubkey for a particular account')
    aparse_pubkey_accountgroup=aparse_pubkey.add_mutually_exclusive_group(required=True)
    aparse_pubkey_accountgroup.add_argument('--account','-a',type=int,help="The number of the hd wallet account to export the pubkey for.")
    aparse_pubkey_accountgroup.add_argument('--root','-r',action='store_true',help="The exported wallet account pubkey is the master extended pubkey.")
    aparse_pubkey.set_defaults(func=pubkey)

    aparse_pubkey = subaparsers.add_parser('privkey',help='[offline] Get the extended HD privkey for a particular account')
    aparse_pubkey_accountgroup=aparse_pubkey.add_mutually_exclusive_group(required=True)
    aparse_pubkey_accountgroup.add_argument('--account','-a',type=int,help="The number of the hd wallet account to export the privkey for.")
    aparse_pubkey_accountgroup.add_argument('--root','-r',action='store_true',help="The exported wallet account privkey is the master extended privkey.")
    aparse_pubkey.set_defaults(func=privkey)

    aparse_address = subaparsers.add_parser('address',help='[online or offline] Get an address for an hd wallet account')
    aparse_address.add_argument('--xpub','-p',required=True,help="The xpubkey for the hdwallet account")
    aparse_address.add_argument('--index','-i','--address',type=int,default=-1,help='The index of the address to get from the account')
    aparse_address.add_argument('--change','-c',action='store_true',help='If present, generates the change address from the account')
    aparse_address.set_defaults(func=address)

    aparse_sign = subaparsers.add_parser('sign',help='[offline] Sign a transaction generated with the send command')
    aparse_sign.add_argument('--input_file','-i',required=True,type=argparse.FileType('r'),help="The input file containing the transaction inputs")
    #aparse_pubkey_accountgroup.add_argument('--account','-a',type=int,help="The number of the hd wallet account to use to sign") #technically this CAN be derived from the transaction xpub
    aparse_sign.set_defaults(func=sign)

    aparse_generate = subaparsers.add_parser('generate',help='[offline] Generate a new hdwallet mnemonic')
    aparse_generate.add_argument('--entropy_bits','--num_bits','-n',type=int,default=128,help='The number of bits of entropy to use to generate the wallet (must be a multiple of 32)')
    aparse_generate.add_argument('--entropy_source','--source','-s',choices=['user','system'],default='system',help='The source of secure entropy to use to generate the wallet')
    aparse_generate.set_defaults(func=generate)

    args = aparser.parse_args()
    if args.no_offline_check:
        REQUIRE_OFFLINE = False

    args.func(args)


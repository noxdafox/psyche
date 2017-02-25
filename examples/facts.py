from psyche import Fact


class Account(Fact):
    name = None

    def __init__(self, name, status='bronze', miles=0):
        self.name = name
        self.status = status
        self.miles = miles


class Flight(Fact):
    def __init__(self, account, airline, miles, category):
        self.account = account
        self.airline = airline
        self.miles = miles
        self.category = category

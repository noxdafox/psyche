class Rule:
    def __init__(self, name, condition, action, salience=0):
        self.name = name
        self.action = action
        self.salience = salience
        self.condition = condition

It's cooking
============

Example
-------

.. code:: python

    import datetime

    from psyche import Fact

    class Employee(Fact):
        name: str
        surname: str
        email: str
        start_date: datetime.date
        active: bool
        salary: int

    rule ChangeEmail:
        """Replace old '.org' company email."""
        condition:
            empl <- Employee(active == True,
                             email.endswith('acme.org'))
        action:
            print(f"Changing employee {empl.surname} email.")
            new_email = empl.email.split('@')[0] + '@acme.com'
            empl.modify(email=new_email)

    rule RaiseSalary:
        """Raise salary if in same role for more than 3 years."""
        condition:
            empl <- Employee(active == True,
                             start_date - date.today() > THREE_YEARS)
        action:
            print(f"Raising {empl.surname} salary.")
            empl.modify(salary+=400)

    THREE_YEARS = datetime.timedelta(weeks=54*3)

It's cooking
============

Example
-------

.. code:: python

    import datetime

    from psyche import Fact

    class Employee(Fact):
        id: int
        name: str
        surname: str
        email: str
        active: bool

    class Role(Fact):
        employee_id: int
        name: str
        salary: int
        start_date: datetime.date
        salary_raise_date: datetime.date

    rule ChangeEmail:
        condition:
            empl <- Employee(active == True,
                             email.endswith('acme.org'))
        action:
            print(f"Changing employee {empl.name} {empl.surname} email")
            new_email = empl.email.split('@')[0] + '@acme.com'
            empl.modify(email=new_email)

    rule RaiseSalary:
        condition:
            empl <- Employee(eid <- id,
                             active == True)
            role <- Role(employee_id == eid,
                         datetime.date.today() - salary_raise_date > THREE_YEARS)
        action:
            print(f"Raising {empl.name} {empl.surname} ({role.name}) salary")
            role.modify(salary=role.salary + 300,
                        salary_raise_date=datetime.date.today())

    THREE_YEARS = datetime.timedelta(weeks=54*3)
